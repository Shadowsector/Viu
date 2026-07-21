@echo off
rem Minimal force update (ASCII). Use if force_update_viu.bat breaks.
cd /d "%~dp0"
set PYTHONUTF8=1
if not defined VIU_UPDATE_BRANCH set "VIU_UPDATE_BRANCH=cursor/viu-agent-core-65c2"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
python bootstrap_update.py --apply
python -m pip install -e . -q --proxy=
if errorlevel 1 (
  python -m pip install -q setuptools wheel --proxy=
  python -m pip install -e . -q --proxy= --no-build-isolation
)
echo Done. Run Viu.cmd
pause
