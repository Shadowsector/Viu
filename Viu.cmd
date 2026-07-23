@echo off
rem Тонкая оболочка: всегда открывает видимую консоль (cmd /k).
cd /d "%~dp0"
if /i "%~1"=="_run" goto :main
start "Viu" cmd /d /k call "%~f0" _run %*
exit /b 0

:main
setlocal EnableExtensions EnableDelayedExpansion
shift
chcp 65001 >nul 2>&1
title Viu — Anabarra
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
set PYTHONWARNINGS=ignore
set "LAUNCH_LOG=%~dp0.viu_launch.log"
set "PIP_LOG=%~dp0.viu_pip.log"
set "STATUS=%~dp0.viu_launch_status"
set "STARTED=%~dp0.viu_gui_started"
set "STARTUP_ERR=%~dp0viu_startup.log"

echo.
echo ===== Viu %DATE% %TIME% =====
echo ===== Viu launch %DATE% %TIME% =====> "%LAUNCH_LOG%"

if /i not "%VIU_KEEP_PROXY%"=="1" (
  if defined HTTPS_PROXY echo [net] HTTPS_PROXY=%HTTPS_PROXY%
  set "HTTP_PROXY="
  set "HTTPS_PROXY="
  set "ALL_PROXY="
  set "http_proxy="
  set "https_proxy="
  set "all_proxy="
  set "PIP_PROXY="
  set "NO_PROXY=*"
  set "no_proxy=*"
)

set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_LLM_TIMEOUT=1200
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_QUIET_HOURS=0-7
set VIU_REFLECT_TEMPERATURE=0.88
set VIU_LAB_VRAM_GB=10
set OLLAMA_MAX_VRAM=10737418240

echo   Папка: %~dp0
echo   Лог:   %LAUNCH_LOG%
if exist "%~dp0viu\package_sha.txt" (
  echo   SHA:   & type "%~dp0viu\package_sha.txt"
) else (
  echo   SHA:   нет viu\package_sha.txt
)
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден в PATH.
  echo [ОШИБКА] Python не найден.>> "%LAUNCH_LOG%"
  goto :fail
)
python --version

if /i "%~1"=="quick" goto :skip_update
if /i "%VIU_QUICK_START%"=="1" goto :skip_update

echo [1/3] GitHub update (может занять несколько минут)...
echo [1/3] updates>> "%LAUNCH_LOG%"
if exist "%~dp0bootstrap_update.py" (
  python bootstrap_update.py --auto 2>&1
  set "BERR=!errorlevel!"
  echo bootstrap exit=!BERR!>> "%LAUNCH_LOG%"
  if !BERR! GEQ 2 (
    echo [net] повтор: bootstrap --apply
    python bootstrap_update.py --apply 2>&1
    set "BERR=!errorlevel!"
  )
  if !BERR! GEQ 1 (
    echo [warn] Обновление не удалось — запускаю текущую версию
  )
) else (
  echo [warn] нет bootstrap_update.py
)
goto :after_update

:skip_update
echo [1/3] Без GitHub (quick). Апдейт: force_update_viu.bat
echo skip update>> "%LAUNCH_LOG%"

:after_update
echo [2/3] .env ...
if not exist "%~dp0.env" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%~dp0.env" >nul

echo [3/3] pip install -e .
python -m pip install -e . -q --proxy= --disable-pip-version-check --no-warn-script-location > "%PIP_LOG%" 2>&1
if errorlevel 1 (
  echo retry pip...
  python -m pip install -q setuptools wheel --proxy= >> "%PIP_LOG%" 2>&1
  python -m pip install -e . -q --proxy= --no-build-isolation --disable-pip-version-check --no-warn-script-location >> "%PIP_LOG%" 2>&1
)
if errorlevel 1 (
  echo [warn] pip fail — пробую GUI как есть. См. %PIP_LOG%
  type "%PIP_LOG%"
)

if exist "%STARTED%" del "%STARTED%" >nul 2>&1
if exist "%STATUS%" del "%STATUS%" >nul 2>&1
if exist "%STARTUP_ERR%" del "%STARTUP_ERR%" >nul 2>&1

echo Запускаю GUI (run_gui.pyw)...
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "ViuGUI" pythonw "%~dp0run_gui.pyw"
) else (
  start "ViuGUI" python "%~dp0run_gui.pyw"
)

set /a _n=0
:waitgui
timeout /t 1 /nobreak >nul
set /a _n+=1
if exist "%STARTED%" goto :guiok
if exist "%STATUS%" (
  findstr /i /c:"already_running" "%STATUS%" >nul 2>&1 && goto :guibusy
  findstr /i /c:"tk_ready" "%STATUS%" >nul 2>&1 && goto :guiok
  findstr /i /c:"running" "%STATUS%" >nul 2>&1 && goto :guiok
  findstr /i /c:"loading" "%STATUS%" >nul 2>&1 && goto :guiok
)
if exist "%STARTUP_ERR%" goto :guicrash
if !_n! LSS 120 goto :waitgui

echo [ОШИБКА] GUI не ответил за 120 сек.
if exist "%STATUS%" type "%STATUS%"
if exist "%STARTUP_ERR%" type "%STARTUP_ERR%"
goto :fail

:guicrash
echo [ОШИБКА] GUI crash:
type "%STARTUP_ERR%"
goto :fail

:guibusy
echo Вью уже запущена. fix_viu_lock.bat или relaunch.cmd
goto :end

:guiok
echo OK — окно Вью открыто.
if exist "%~dp0viu\package_sha.txt" type "%~dp0viu\package_sha.txt"
goto :end

:fail
echo.
echo ---- см. %LAUNCH_LOG% ----

:end
echo.
echo Консоль можно закрыть. Диагностика: diag_viu_launch.bat
pause
exit /b 0
