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


def test_already_running_summary_explains_empty_queue(monkeypatch, tmp_path):
    from viu.config import Config
    from viu.integrations.comfy.client import ComfyClient

    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu")
    (tmp_path / ".viu").mkdir(parents=True)
    monkeypatch.setattr(comfy_process, "_pids_on_port", lambda port: [])
    monkeypatch.setattr(comfy_process, "open_comfy_browser", lambda cfg: "")
    monkeypatch.setattr(
        "viu.integrations.comfy.face_refs.face_swap_status_line",
        lambda cfg, client=None: "face_swap: OK",
    )
    client = ComfyClient(base_url="http://127.0.0.1:8188", timeout=1.0)
    text = comfy_process._already_running_summary(
        cfg,
        client,
        ping_msg="ComfyUI OK http://127.0.0.1:8188 (running=0, pending=0)",
        port=8188,
        torch_line="torch=2.x CUDA=yes",
    )
    assert "running=0" in text
    assert "Снять" in text or "очередь" in text.lower()
    assert "8188" in text
    assert "face_swap" in text
