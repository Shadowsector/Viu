"""Диагностика: кто слушает :8188 (не путать с python Вью)."""

from viu.integrations.comfy import process as comfy_process


def test_looks_like_comfy_process():
    assert comfy_process._looks_like_comfy_process(
        {
            "name": "python.exe",
            "exe": r"U:\Viu\ComfyUI\python_embeded\python.exe",
            "cmdline": r'U:\Viu\ComfyUI\python_embeded\python.exe -u U:\Viu\ComfyUI\main.py --port 8188',
        }
    )
    assert comfy_process._looks_like_comfy_process(
        {"name": "ComfyUI.exe", "exe": r"C:\Program Files\ComfyUI\ComfyUI.exe", "cmdline": ""}
    )
    assert not comfy_process._looks_like_comfy_process(
        {
            "name": "python.exe",
            "exe": r"U:\Anabarra\Viu\.venv\Scripts\python.exe",
            "cmdline": r"python.exe -m viu",
        }
    )


def test_describe_port_listeners_empty(monkeypatch):
    monkeypatch.setattr(comfy_process, "_pids_on_port", lambda port: [])
    text = comfy_process.describe_port_listeners(8188)
    assert ":8188" in text
    assert "python_embeded" in text.lower() or "comfyui" in text.lower()


def test_describe_port_listeners_with_pid(monkeypatch):
    monkeypatch.setattr(comfy_process, "_pids_on_port", lambda port: [4242])
    monkeypatch.setattr(
        comfy_process,
        "_process_identity",
        lambda pid: {
            "pid": pid,
            "name": "python.exe",
            "exe": r"U:\Viu\ComfyUI\python_embeded\python.exe",
            "cmdline": r"python.exe -u main.py --port 8188",
        },
    )
    text = comfy_process.describe_port_listeners(8188)
    assert "pid=4242" in text
    assert "это Comfy" in text
    assert "python_embeded" in text
