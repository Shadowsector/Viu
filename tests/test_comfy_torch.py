"""Torch preflight: CUDA stack by Python version."""

from pathlib import Path
from unittest.mock import patch

from viu.integrations.comfy import process as comfy_proc


def test_cuda_stacks_py314_skips_cu124():
    stacks = comfy_proc.cuda_stacks_for_python(3, 14)
    labels = [s[0] for s in stacks]
    assert labels
    assert all(not lab.startswith("cu124") for lab in labels)
    assert any(lab.startswith("cu126") for lab in labels)


def test_cuda_stacks_py312_prefers_cu124():
    stacks = comfy_proc.cuda_stacks_for_python(3, 12)
    assert stacks[0][0].startswith("cu124")


def test_ensure_torch_tries_cu126_on_py314(tmp_path):
    calls: list[list[str]] = []
    info_n = {"n": 0}

    def fake_info(py, root):
        info_n["n"] += 1
        if info_n["n"] == 1:
            return True, "2.13.0+cpu", False
        return True, "2.13.0+cu126", True

    def fake_pip(py, args, *, cwd):
        calls.append(list(args))
        # fail cu124-style if present; succeed on cu126
        joined = " ".join(args)
        if "cu124" in joined or "cu121" in joined:
            return False, "from versions: none"
        if "cu126" in joined:
            return True, "ok"
        return False, "fail"

    with (
        patch.object(comfy_proc, "nvidia_gpu_available", return_value=True),
        patch.object(comfy_proc, "_python_version", return_value=(3, 14)),
        patch.object(comfy_proc, "_torch_info", side_effect=fake_info),
        patch.object(comfy_proc, "_pip_install", side_effect=fake_pip),
        patch.object(comfy_proc, "_pip_uninstall_torch", return_value="uninstalled"),
    ):
        ok, msg = comfy_proc.ensure_torch_for_comfy(tmp_path, Path("python"))
    assert ok
    assert any("cu126" in " ".join(c) for c in calls)
    assert "cu126" in msg or "CUDA=yes" in msg


def test_ensure_torch_uninstalls_cpu_before_cuda(tmp_path):
    calls: list[list[str]] = []

    def fake_info(py, root):
        if not any(c and c[0] == "--no-cache-dir" for c in calls):
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
        patch.object(comfy_proc, "_python_version", return_value=(3, 12)),
        patch.object(comfy_proc, "_torch_info", side_effect=fake_info),
        patch.object(comfy_proc, "_pip_install", side_effect=fake_pip),
        patch.object(comfy_proc, "_pip_uninstall_torch", side_effect=fake_uninstall),
    ):
        ok, msg = comfy_proc.ensure_torch_for_comfy(tmp_path, Path("python"))
    assert ok
    assert any(c == ["uninstall"] for c in calls)
    install = next(c for c in calls if c and c[0] == "--no-cache-dir")
    assert "--force-reinstall" in install
    assert any("cu124" in a or "2.6.0" in a for a in install)


def test_ensure_torch_cpu_fallback_message(tmp_path):
    def fake_info(py, root):
        return True, "2.13.0+cpu", False

    with (
        patch.object(comfy_proc, "nvidia_gpu_available", return_value=True),
        patch.object(comfy_proc, "_python_version", return_value=(3, 14)),
        patch.object(comfy_proc, "_torch_info", side_effect=fake_info),
        patch.object(comfy_proc, "_pip_uninstall_torch", return_value="ok"),
        patch.object(comfy_proc, "_pip_install", return_value=(True, "ok")),
    ):
        ok, msg = comfy_proc.ensure_torch_for_comfy(tmp_path, Path("python"))
    assert ok
    assert "--cpu" in msg or "без CUDA" in msg
