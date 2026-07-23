"""Безопасный subprocess с текстом на Windows (Unity → cp1251, PYTHONUTF8=1)."""

from __future__ import annotations

import locale
import subprocess
import sys
from typing import Any, Mapping, Sequence, Union

Cmd = Union[str, Sequence[str]]


def pipe_encoding() -> str:
    """Кодировка stdout/stderr внешних процессов (Unity batch, tasklist)."""
    if sys.platform == "win32":
        return locale.getpreferredencoding(False) or "cp1251"
    return "utf-8"


def run_text(
    cmd: Cmd,
    *,
    timeout: float | None = None,
    cwd: str | None = None,
    shell: bool = False,
    capture_output: bool = True,
    check: bool = False,
    env: Mapping[str, str] | None = None,
    creationflags: int = 0,
) -> subprocess.CompletedProcess[str]:
    """subprocess.run с text=True — не падает на русском выводе Unity."""
    kwargs: dict[str, Any] = {
        "shell": shell,
        "capture_output": capture_output,
        "text": True,
        "encoding": pipe_encoding(),
        "errors": "replace",
        "check": check,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    if cwd is not None:
        kwargs["cwd"] = cwd
    if env is not None:
        kwargs["env"] = dict(env)
    if creationflags:
        kwargs["creationflags"] = creationflags
    return subprocess.run(cmd, **kwargs)  # noqa: S603
