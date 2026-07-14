"""Torch preflight: CPU+cu124 force-replace."""

from pathlib import Path
from unittest.mock import patch

from viu.integrations.comfy import process as comfy_proc


def test_ensure_torch_uninstalls_cpu_before_cu124(tmp_path):
    calls: list[list[str]] = []

    def fake_info(py, root):
        if not calls:
            return True, "2.13.0+cpu", False
        return True, "2.6.0+cu124", True

    def fake_pip(py, args, *, cwd):
        calls.append(list(args))
        return True, "ok"

    def fake_uninstall(py, *, cwd):
        calls.append(["uninstall"])
        return "uninstalled"

    with (
        patch.object(comfy_proc, "nvidia_gpu_available", return_value=True),
        patch.object(comfy_proc, "_torch_info", side_effect=fake_info),
        patch.object(comfy_proc, "_pip_install", side_effect=fake_pip),
        patch.object(comfy_proc, "_pip_uninstall_torch", side_effect=fake_uninstall),
    ):
        ok, msg = comfy_proc.ensure_torch_for_comfy(tmp_path, Path("python"))
    assert ok
    assert any(c == ["uninstall"] for c in calls)
    install = next(c for c in calls if c and c[0] == "--no-cache-dir")
    assert "--force-reinstall" in install
    assert any("2.6.0+cu124" in a for a in install)
    assert "сношу" in msg or "cu124" in msg


def test_ensure_torch_cpu_fallback_message(tmp_path):
    def fake_info(py, root):
        return True, "2.13.0+cpu", False

    with (
        patch.object(comfy_proc, "nvidia_gpu_available", return_value=True),
        patch.object(comfy_proc, "_torch_info", side_effect=fake_info),
        patch.object(comfy_proc, "_pip_uninstall_torch", return_value="ok"),
        patch.object(comfy_proc, "_pip_install", return_value=(True, "ok")),
    ):
        ok, msg = comfy_proc.ensure_torch_for_comfy(tmp_path, Path("python"))
    assert ok
    assert "--cpu" in msg or "без CUDA" in msg
