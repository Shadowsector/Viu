import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from viu.config import Config
from viu.integrations.blender import (
    BlenderClient,
    build_dump_command,
    dispatch,
    make_error,
    make_ok,
)
from viu.integrations.blender.headless import dump_blend_info, parse_dump_output
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.blender_tool import BlenderCommandTool, BlenderInfoTool


# --------- Протокол ---------

def test_dispatch_unknown_command():
    r = dispatch("nope", {}, {})
    assert not r["ok"] and "неизвестная" in r["error"]


def test_dispatch_missing_params():
    r = dispatch("object_info", {}, {"object_info": lambda p: p})
    assert not r["ok"] and "не хватает" in r["error"]


def test_dispatch_routes_and_wraps():
    handlers = {"ping": lambda p: {"pong": True}}
    r = dispatch("ping", {}, handlers)
    assert r == make_ok({"pong": True})


def test_dispatch_handler_exception_becomes_error():
    def boom(_):
        raise ValueError("бум")

    r = dispatch("ping", {}, {"ping": boom})
    assert not r["ok"] and "бум" in r["error"]


# --------- Клиент против реального локального HTTP-моста ---------

FAKE_HANDLERS = {
    "ping": lambda p: {"blender": "test"},
    "scene_info": lambda p: {"objects": [{"name": "Куб", "type": "MESH"}]},
    "set_shape_key": lambda p: {"object": p["object"], "key": p["key"], "value": p["value"]},
}


class _FakeBridge(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        result = dispatch(body["command"], body.get("params", {}), FAKE_HANDLERS)
        data = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def bridge():
    server = HTTPServer(("127.0.0.1", 0), _FakeBridge)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()


def test_client_ping_and_scene(bridge):
    client = BlenderClient(port=bridge)
    assert client.is_alive()
    scene = client.scene_info()
    assert scene["objects"][0]["name"] == "Куб"


def test_client_set_shape_key_roundtrip(bridge):
    client = BlenderClient(port=bridge)
    r = client.set_shape_key("Лицо", "улыбка", 0.7)
    assert r == {"object": "Лицо", "key": "улыбка", "value": 0.7}


def test_client_unknown_command_raises(bridge):
    from viu.integrations.blender import BlenderBridgeError

    client = BlenderClient(port=bridge)
    with pytest.raises(BlenderBridgeError):
        client._post("object_info", {"name": "нет"})  # нет обработчика в FAKE_HANDLERS


def test_client_no_connection_is_not_alive():
    # Порт, где точно никто не слушает.
    client = BlenderClient(port=59999, timeout=1.0)
    assert client.is_alive() is False


# --------- Headless (фоновый Blender) ---------

def test_build_dump_command():
    cmd = build_dump_command("blender", "/x/y.blend", "/tmp/s.py")
    assert cmd[0] == "blender"
    assert "--background" in cmd and "--python" in cmd
    assert "/x/y.blend" in cmd


def test_parse_dump_output():
    from viu.integrations.blender.headless import _MARK_BEGIN, _MARK_END

    payload = {"objects": [{"name": "A"}]}
    out = f"шум\n{_MARK_BEGIN}{json.dumps(payload)}{_MARK_END}\nещё шум"
    assert parse_dump_output(out) == payload


def test_dump_blend_info_with_mock_runner(tmp_path):
    from viu.integrations.blender.headless import _MARK_BEGIN, _MARK_END

    blend = tmp_path / "model.blend"
    blend.write_text("")  # достаточно, чтобы файл существовал

    payload = {"objects": [{"name": "Шаня", "type": "MESH", "shape_keys": ["улыбка"]}]}

    class _Proc:
        returncode = 0
        stdout = f"{_MARK_BEGIN}{json.dumps(payload, ensure_ascii=False)}{_MARK_END}"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        assert str(blend) in cmd
        return _Proc()

    data = dump_blend_info(str(blend), runner=fake_runner)
    assert data["objects"][0]["shape_keys"] == ["улыбка"]


def test_dump_blend_info_missing_file():
    with pytest.raises(FileNotFoundError):
        dump_blend_info("/no/such/file.blend")


# --------- Инструменты Вью ---------

@pytest.fixture
def ctx(tmp_path):
    # Порт, где никто не слушает -> мост «мёртв».
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", blender_port=59998).ensure_dirs()
    registry = build_default_registry()
    return AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=registry,
    )


def test_blender_info_no_bridge_no_file(ctx):
    r = BlenderInfoTool().run({}, ctx)
    assert not r.ok and "не запущен" in r.content.lower()


def test_blender_info_headless(ctx, monkeypatch, tmp_path):
    import viu.tools.blender_tool as bt

    monkeypatch.setattr(bt, "dump_blend_info", lambda *a, **k: {"objects": [{"name": "Куб"}]})
    r = BlenderInfoTool().run({"blend_file": str(tmp_path / "x.blend")}, ctx)
    assert r.ok and "Куб" in r.content


def test_blender_command_unknown(ctx):
    r = BlenderCommandTool().run({"command": "fly_to_moon"}, ctx)
    assert not r.ok and "не поддерживается" in r.content


def test_blender_registry_registered():
    reg = build_default_registry()
    for name in ("blender_info", "blender_command", "blender_screenshot"):
        assert reg.get(name) is not None, name
