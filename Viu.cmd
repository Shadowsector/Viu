@echo off
rem ============================================================
rem   VIU — запусти двойным кликом.
rem   Лог запуска: U:\Viu\.viu_launch.log
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title Viu — Anabarra
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
set PYTHONWARNINGS=ignore
set "LAUNCH_LOG=%~dp0.viu_launch.log"
set "PIP_LOG=%~dp0.viu_pip.log"
set "STATUS=%~dp0.viu_launch_status"
set "STARTED=%~dp0.viu_gui_started"
set "STARTUP_ERR=%~dp0viu_startup.log"

echo ===== Viu launch %DATE% %TIME% =====> "%LAUNCH_LOG%"

rem --- Мёртвый локальный прокси (Clash/V2Ray) ломает pip/GitHub ---
if /i not "%VIU_KEEP_PROXY%"=="1" (
  if defined HTTPS_PROXY echo [net] Снимаю HTTPS_PROXY=%HTTPS_PROXY%>> "%LAUNCH_LOG%"
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

rem --- дефолты, если в .env нет строки (`.env` перекрывает эти ключи) ---
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_LLM_TIMEOUT=1200
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_QUIET_HOURS=0-7
set VIU_REFLECT_TEMPERATURE=0.88
rem Лимит VRAM для Ollama (LLM). Перезапусти Ollama из трея после смены.
set VIU_LAB_VRAM_GB=10
set OLLAMA_MAX_VRAM=10737418240
rem Модели — из .env (VIU_MODEL_REFLECT=viu-cydonia …). Не форсим coder здесь.
rem ---------------------------------

echo.
echo   Готовлю Вью...
echo   Лог: %LAUNCH_LOG%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден.
  echo [ОШИБКА] Python не найден.>> "%LAUNCH_LOG%"
  goto :fail
)

echo [1/3] Проверяю обновления...
echo [1/3] updates>> "%LAUNCH_LOG%"
if exist "%~dp0bootstrap_update.py" (
  python bootstrap_update.py --auto >> "%LAUNCH_LOG%" 2>&1
  if errorlevel 2 (
    echo [net] GitHub новее — принудительный zip --apply>> "%LAUNCH_LOG%"
    python bootstrap_update.py --apply >> "%LAUNCH_LOG%" 2>&1
  )
  if errorlevel 1 (
    echo [warn] Обновление не удалось — запускаю текущую версию>> "%LAUNCH_LOG%"
  )
)

echo [2/3] Файл настроек .env...
if not exist "%~dp0.env" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%~dp0.env" >nul

echo [3/3] Пакет + запуск окна...
echo [3/3] pip>> "%LAUNCH_LOG%"
python -m pip install -e . -q --proxy= --disable-pip-version-check --no-warn-script-location > "%PIP_LOG%" 2>&1
if errorlevel 1 (
  echo [net] setuptools + no-build-isolation...
  echo retry setuptools>> "%LAUNCH_LOG%"
  python -m pip install -q setuptools wheel --proxy= >> "%PIP_LOG%" 2>&1
  python -m pip install -e . -q --proxy= --no-build-isolation --disable-pip-version-check --no-warn-script-location >> "%PIP_LOG%" 2>&1
)
if errorlevel 1 (
  echo [ОШИБКА] pip не смог установить Viu.
  echo ---- pip log ---->> "%LAUNCH_LOG%"
  type "%PIP_LOG%" >> "%LAUNCH_LOG%"
  type "%PIP_LOG%"
  goto :fail
)

rem убрать маркеры прошлого запуска
if exist "%STARTED%" del "%STARTED%" >nul 2>&1
if exist "%STATUS%" del "%STATUS%" >nul 2>&1
if exist "%STARTUP_ERR%" del "%STARTUP_ERR%" >nul 2>&1

echo Запускаю GUI...
echo starting GUI>> "%LAUNCH_LOG%"
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "ViuGUI" pythonw "%~dp0run_gui.pyw"
) else (
  start "ViuGUI" python "%~dp0run_gui.pyw"
)

rem Ждём до 45 сек: started / already_running / ошибка
set /a _n=0
:waitgui
timeout /t 1 /nobreak >nul
set /a _n+=1
if exist "%STARTED%" goto :guiok
if exist "%STATUS%" (
  findstr /i /c:"already_running" "%STATUS%" >nul 2>&1
  if not errorlevel 1 goto :guibusy
)
if exist "%STARTUP_ERR%" goto :guicrash
if %_n% LSS 45 goto waitgui

echo.
echo [ОШИБКА] Окно Вью не открылось за 45 сек.
echo Статус:
if exist "%STATUS%" type "%STATUS%"
if exist "%STARTUP_ERR%" type "%STARTUP_ERR%"
echo.
echo Если Вью «висит» в фоне — Диспетчер задач: заверши python/pythonw,
echo или запусти fix_viu_lock.bat
echo timeout waiting for GUI>> "%LAUNCH_LOG%"
if exist "%STATUS%" type "%STATUS%" >> "%LAUNCH_LOG%"
goto :fail

:guicrash
echo.
echo [ОШИБКА] GUI упал при старте:
type "%STARTUP_ERR%"
type "%STARTUP_ERR%" >> "%LAUNCH_LOG%"
goto :fail

:guibusy
echo.
echo Вью уже запущена — ищи окно на панели задач.
echo Если окна нет: Диспетчер задач -^> сними python/pythonw, или fix_viu_lock.bat
echo already_running>> "%LAUNCH_LOG%"
echo.
echo Нажми клавишу...
pause >nul
exit /b 0

:guiok
echo Окно Вью открыто.
echo GUI started OK>> "%LAUNCH_LOG%"
exit /b 0

:fail
echo.
echo ---- Лог: %LAUNCH_LOG% ----
echo Нажми любую клавишу, чтобы закрыть...
pause >nul
exit /b 1
