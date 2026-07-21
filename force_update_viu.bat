@echo off
rem Force-update Viu from GitHub (zip). ASCII-only for cmd.exe.
cd /d "%~dp0"
title Viu force update
set PYTHONUTF8=1

if not defined VIU_UPDATE_BRANCH set "VIU_UPDATE_BRANCH=cursor/viu-agent-core-65c2"

if /i not "%VIU_KEEP_PROXY%"=="1" (
  set "HTTP_PROXY="
  set "HTTPS_PROXY="
  set "ALL_PROXY="
  set "NO_PROXY=*"
)

echo.
echo   Viu force update
echo   Branch: %VIU_UPDATE_BRANCH%
echo.

where python >nul 2>&1
if errorlevel 1 goto no_python

echo [1/2] bootstrap_update.py --apply
python bootstrap_update.py --apply
if errorlevel 1 goto try_viu_cli
goto pip_step

:try_viu_cli
echo [1/2] fallback: python -m viu update --apply --force
python -m viu update --apply --force
if errorlevel 1 goto update_failed

:pip_step
echo [2/2] pip install -e .
python -m pip install -e . -q --proxy= --disable-pip-version-check
if errorlevel 1 python -m pip install -e . -q --proxy= --no-build-isolation --disable-pip-version-check

echo.
echo Done. Close all Viu windows, then run Viu.cmd
echo Check: type viu\package_sha.txt
echo.
pause
exit /b 0

:no_python
echo ERROR: Python not found in PATH.
pause
exit /b 1

:update_failed
echo ERROR: update failed. See messages above.
pause
exit /b 1
