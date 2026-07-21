@echo off
rem ComfyUI install через Вью (не отдельная exe).
rem Примеры:
rem   comfy_install.bat
rem   comfy_install.bat reactor=1
rem   comfy_install.bat i2v=1
rem   comfy_install.bat reactor=1 models=0
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "JSON={"
set "FIRST=1"
for %%A in (%*) do (
  for /f "tokens=1,2 delims==" %%K in ("%%A") do (
    set "K=%%K"
    set "V=%%L"
    if not "!FIRST!"=="1" set "JSON=!JSON!, "
    set "JSON=!JSON!\"!K!\":\"!V!\""
    set "FIRST=0"
  )
)
set "JSON=!JSON!}"

if "%FIRST%"=="1" set "JSON={}"

echo comfy_install --args !JSON!
python -m viu tool comfy_install --args "!JSON!"
set "EC=%ERRORLEVEL%"
if %EC% NEQ 0 pause
exit /b %EC%
