"""Протокол моста Blender: команды, валидация, маршрутизация.

Модуль намеренно НЕ зависит от Blender (bpy), чтобы его можно было
использовать и тестировать со стороны Вью, и переиспользовать внутри
надстройки Blender.

Формат запроса:  {"command": "<имя>", "params": {...}}
Формат ответа:   {"ok": true, "data": ...}  либо  {"ok": false, "error": "..."}
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

# Имя команды -> список обязательных параметров.
COMMANDS: Dict[str, List[str]] = {
    "ping": [],
    "scene_info": [],            # объекты, меши, арматуры, материалы в текущей сцене
    "object_info": ["name"],     # подробности по объекту (в т.ч. блендшейпы, модификаторы)
    "list_shape_keys": ["object"],
    "set_shape_key": ["object", "key", "value"],
    "run_operator": ["operator"],  # вызвать оператор Blender (аналог нажатия кнопки)
    "screenshot": [],            # снимок вьюпорта (для vision-модели), опц. параметр path
    "rename_bones": ["armature", "mapping"],  # переименовать кости арматуры по плану
    "list_sockets": [],          # перечислить сокеты (Empty-метки) сцены
    "append_object": ["blend_file", "object"],  # добавить объект из другого .blend
}


def make_ok(data: Any) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def make_error(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message}


def dispatch(
    command: str,
    params: Dict[str, Any],
    handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
) -> Dict[str, Any]:
    """Проверяет команду и вызывает соответствующий обработчик.

    Обработчики принимают dict параметров и возвращают любые данные
    (сериализуемые в JSON). Исключения перехватываются и превращаются в ошибку.
    """
    if command not in COMMANDS:
        return make_error(f"неизвестная команда: {command!r}")

    params = params or {}
    missing = [p for p in COMMANDS[command] if p not in params]
    if missing:
        return make_error(f"не хватает параметров: {', '.join(missing)}")

    handler = handlers.get(command)
    if handler is None:
        return make_error(f"нет обработчика для команды: {command!r}")

    try:
        return make_ok(handler(params))
    except Exception as exc:  # noqa: BLE001 — любая ошибка обработчика -> в ответ
        return make_error(f"{type(exc).__name__}: {exc}")
