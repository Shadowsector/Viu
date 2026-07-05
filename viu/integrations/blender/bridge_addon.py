"""Надстройка (add-on) моста Вью для Blender.

Устанавливается ВНУТРЬ Blender (Edit > Preferences > Add-ons > Install from Disk),
после чего Blender слушает локальные команды от Вью на http://127.0.0.1:8765/.

Важно: bpy не потокобезопасен, поэтому HTTP-сервер работает в отдельном потоке,
а сами команды Blender выполняются в главном потоке через таймер bpy.app.timers.

Файл самодостаточный (не импортирует другие модули Вью), чтобы его можно было
поставить в Blender одним файлом.
"""

bl_info = {
    "name": "Viu Bridge",
    "author": "Viu",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Автозапуск при включении надстройки",
    "description": "Мост для управления Blender агентом Вью по HTTP (localhost)",
    "category": "System",
}

import json
import os
import queue
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import bpy

HOST = os.environ.get("VIU_BLENDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIU_BLENDER_PORT", "8765"))

# Очередь заданий: HTTP-поток кладёт сюда, главный поток Blender выполняет.
_job_queue: "queue.Queue" = queue.Queue()
_server = None
_server_thread = None


# --- Мини-протокол (копия viu/integrations/blender/protocol.py, чтобы файл был автономным) ---

COMMANDS = {
    "ping": [],
    "scene_info": [],
    "object_info": ["name"],
    "list_shape_keys": ["object"],
    "set_shape_key": ["object", "key", "value"],
    "run_operator": ["operator"],
    "screenshot": [],
    "rename_bones": ["armature", "mapping"],
}


def _make_ok(data):
    return {"ok": True, "data": data}


def _make_error(msg):
    return {"ok": False, "error": msg}


# --- Обработчики команд (исполняются в главном потоке Blender) ---

def _h_ping(_params):
    return {"blender": bpy.app.version_string, "addon": "viu-bridge 0.1.0"}


def _obj_brief(o):
    info = {"name": o.name, "type": o.type}
    data = o.data
    if o.type == "MESH" and data is not None:
        info["vertices"] = len(data.vertices)
        info["shape_keys"] = (
            [kb.name for kb in data.shape_keys.key_blocks] if data.shape_keys else []
        )
        info["materials"] = [m.name for m in data.materials if m]
        info["modifiers"] = [m.name for m in o.modifiers]
    if o.type == "ARMATURE" and data is not None:
        info["bones"] = [b.name for b in data.bones]
    return info


def _h_scene_info(_params):
    return {
        "file": bpy.data.filepath,
        "objects": [_obj_brief(o) for o in bpy.data.objects],
        "armatures": [a.name for a in bpy.data.armatures],
        "materials": [m.name for m in bpy.data.materials],
        "actions": [a.name for a in bpy.data.actions],
    }


def _h_object_info(params):
    o = bpy.data.objects.get(params["name"])
    if o is None:
        raise KeyError(f"объект не найден: {params['name']}")
    return _obj_brief(o)


def _h_list_shape_keys(params):
    o = bpy.data.objects.get(params["object"])
    if o is None or o.type != "MESH":
        raise KeyError(f"меш не найден: {params['object']}")
    if not o.data.shape_keys:
        return []
    return [
        {"name": kb.name, "value": kb.value}
        for kb in o.data.shape_keys.key_blocks
    ]


def _h_set_shape_key(params):
    o = bpy.data.objects.get(params["object"])
    if o is None or o.type != "MESH" or not o.data.shape_keys:
        raise KeyError(f"нет блендшейпов у объекта: {params['object']}")
    kb = o.data.shape_keys.key_blocks.get(params["key"])
    if kb is None:
        raise KeyError(f"блендшейп не найден: {params['key']}")
    kb.value = float(params["value"])
    return {"object": o.name, "key": kb.name, "value": kb.value}


def _h_run_operator(params):
    # "mesh.primitive_cube_add" -> bpy.ops.mesh.primitive_cube_add(**args)
    op_path = params["operator"].replace("bpy.ops.", "")
    target = bpy.ops
    for part in op_path.split("."):
        target = getattr(target, part)
    result = target(**(params.get("args") or {}))
    return {"operator": params["operator"], "result": list(result)}


def _h_screenshot(params):
    path = params.get("path") or os.path.join(tempfile.gettempdir(), "viu_blender_view.png")
    bpy.ops.screen.screenshot(filepath=path)
    return {"path": path}


def _h_rename_bones(params):
    arm = bpy.data.objects.get(params["armature"])
    if arm is None or arm.type != "ARMATURE":
        raise KeyError(f"арматура не найдена: {params['armature']}")
    mapping = params["mapping"] or {}

    prev_active = bpy.context.view_layer.objects.active
    prev_mode = arm.mode if arm == prev_active else "OBJECT"
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    renamed = []
    try:
        for old, new in mapping.items():
            eb = arm.data.edit_bones.get(old)
            if eb is not None:
                eb.name = new
                renamed.append([old, new])
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if prev_active is not None:
            bpy.context.view_layer.objects.active = prev_active
    return {"armature": arm.name, "renamed": renamed}


_HANDLERS = {
    "ping": _h_ping,
    "scene_info": _h_scene_info,
    "object_info": _h_object_info,
    "list_shape_keys": _h_list_shape_keys,
    "set_shape_key": _h_set_shape_key,
    "run_operator": _h_run_operator,
    "screenshot": _h_screenshot,
    "rename_bones": _h_rename_bones,
}


def _dispatch(command, params):
    if command not in COMMANDS:
        return _make_error(f"неизвестная команда: {command!r}")
    params = params or {}
    missing = [p for p in COMMANDS[command] if p not in params]
    if missing:
        return _make_error(f"не хватает параметров: {', '.join(missing)}")
    try:
        return _make_ok(_HANDLERS[command](params))
    except Exception as exc:  # noqa: BLE001
        return _make_error(f"{type(exc).__name__}: {exc}")


# --- Главный поток: выполнение заданий из очереди ---

def _process_queue():
    while not _job_queue.empty():
        job = _job_queue.get_nowait()
        job["result"] = _dispatch(job["command"], job["params"])
        job["event"].set()
    return 0.05  # снова вызвать через 50 мс


# --- HTTP-сервер (отдельный поток) ---

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # тише в консоли Blender
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            command = body.get("command", "")
            params = body.get("params", {})
        except (ValueError, KeyError):
            self._send({"ok": False, "error": "некорректный JSON запроса"})
            return

        # Передаём задание в главный поток и ждём результат.
        event = threading.Event()
        job = {"command": command, "params": params, "event": event, "result": None}
        _job_queue.put(job)
        if not event.wait(timeout=30):
            self._send({"ok": False, "error": "таймаут выполнения в Blender"})
            return
        self._send(job["result"])

    def _send(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _start_server():
    global _server, _server_thread
    if _server is not None:
        return
    _server = HTTPServer((HOST, PORT), _Handler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    print(f"[Viu Bridge] слушаю http://{HOST}:{PORT}/")


def _stop_server():
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
        _server_thread = None
        print("[Viu Bridge] остановлен")


def register():
    _start_server()
    if not bpy.app.timers.is_registered(_process_queue):
        bpy.app.timers.register(_process_queue, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_process_queue):
        bpy.app.timers.unregister(_process_queue)
    _stop_server()


if __name__ == "__main__":
    register()
