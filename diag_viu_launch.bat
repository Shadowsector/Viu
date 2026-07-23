@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Viu diagnostic
echo === Viu launch diagnostic ===
echo.
echo CWD: %CD%
echo.
echo --- python ---
where python 2>nul || echo python NOT in PATH
python --version 2>nul
echo.
echo --- pythonw ---
where pythonw 2>nul || echo pythonw NOT in PATH
echo.
echo --- files ---
if exist Viu.cmd (echo OK Viu.cmd) else (echo MISSING Viu.cmd)
if exist run_gui.pyw (echo OK run_gui.pyw) else (echo MISSING run_gui.pyw)
if exist bootstrap_update.py (echo OK bootstrap_update.py) else (echo MISSING bootstrap_update.py)
if exist viu\package_sha.txt (
  echo SHA:
  type viu\package_sha.txt
) else (
  echo no viu\package_sha.txt
)
echo.
echo --- import viu ---
python -c "import viu; from viu.updater import version_label,running_sha; print(version_label(), (running_sha() or '')[:12])" 2>&1
echo.
echo --- port 47615 ---
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 47615 -ErrorAction SilentlyContinue | Format-Table -AutoSize"
echo.
echo --- last launch log (tail) ---
if exist .viu_launch.log (
  powershell -NoProfile -Command "Get-Content -Path '.viu_launch.log' -Tail 25"
) else (
  echo no .viu_launch.log
)
echo.
echo --- viu_startup.log ---
if exist viu_startup.log type viu_startup.log
echo.
pause
