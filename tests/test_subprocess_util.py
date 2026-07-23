"""Тесты subprocess_util."""

from __future__ import annotations

import locale
import subprocess
import sys

from viu.subprocess_util import pipe_encoding, run_text


def test_pipe_encoding_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda _=False: "cp1251")
    assert pipe_encoding() == "cp1251"


def test_run_text_does_not_require_utf8_stdout():
    proc = run_text([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x88ok\\n')"], timeout=30)
    assert proc.stdout is not None
    assert "ok" in proc.stdout
