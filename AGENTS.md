# AGENTS.md

## Cursor Cloud specific instructions

Viu (Вью) is a single Python 3.10+ package: an offline-capable ReAct AI agent with a
CLI and a tkinter desktop GUI. Runtime uses only the standard library; the sole dev
dependency is `pytest`. Install and standard commands are in `README.md`
(`pip install -e ".[dev]"`, `pytest -q`, `python -m viu ...`). External integrations
(Ollama, Unity, Blender, ComfyUI, Cascadeur, Telegram) are Windows/GPU oriented and are
out of scope for this cloud VM — the agent core, CLI, demo, tests, and GUI all run
offline with the built-in `mock` LLM provider.

Non-obvious caveats:

- **tkinter is required at import time.** The `viu` package imports `tkinter` transitively
  during normal imports (e.g. `viu.prop_catalog`), so without it *every* import and test
  fails with `ModuleNotFoundError: No module named 'tkinter'`. The system package
  `python3-tk` is baked into the VM snapshot. If you ever see that error, reinstall it with
  `sudo apt-get install -y python3-tk` (it is not a pip dependency).
- **The GUI auto-updates over the working tree — disable it.** Launching the GUI
  (`run_gui.pyw` / `Viu.cmd`) triggers an auto-updater that downloads a GitHub zip of
  `VIU_UPDATE_BRANCH` and unpacks it *on top of* the repo, clobbering local changes and
  looping. Always launch with `VIU_AUTO_UPDATE=0` set. The GUI needs a display; `DISPLAY=:1`
  is available on this VM.
- **Provider config comes from `.env`, not just env vars.** On first run the GUI's
  `bootstrap_env` copies `.env.example` → `.env` (gitignored), which defaults
  `VIU_PROVIDER=openai` pointing at Ollama on `localhost:11434`. For a fully offline run,
  set `VIU_PROVIDER=mock` **inside `.env`** (the file overrides the process env var).
  The CLI (`python -m viu demo` / `run`) defaults to `mock` and needs no `.env`.
- **`viu` console script lands in `~/.local/bin`** (not on PATH by default). Prefer
  `python -m viu ...`, or add that dir to PATH.
- **No linter is configured** (no ruff/flake8/black); there is no lint step.
- **Pre-existing test failures.** `pytest -q` yields ~607 passed with ~14 failures that are
  pre-existing and unrelated to environment setup: Windows-only path assumptions (e.g.
  `venv/Scripts/python.exe`) and assertion drift in code. Do not treat these as setup breakage.
- **`.bat`/`.cmd` files always show as modified** in `git status` due to `.gitattributes`
  `eol=crlf` renormalization. Do not stage them.
