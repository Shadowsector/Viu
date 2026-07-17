@echo off
rem ============================================================
rem   VIU — запусти двойным кликом. Это единственный нужный файл.
rem   Консоль сама закроется, окно Вью откроется отдельно.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title Viu — Anabarra
set PYTHONUTF8=1
set PYTHONPATH=%~dp0

rem --- Мёртвый локальный прокси (Clash/V2Ray на 127.0.0.1) ломает pip/GitHub ---
rem Если свой прокси реально нужен: set VIU_KEEP_PROXY=1
if /i not "%VIU_KEEP_PROXY%"=="1" (
  if defined HTTPS_PROXY echo [net] Снимаю HTTPS_PROXY=%HTTPS_PROXY% ^(прокси не отвечает^)
  if defined HTTP_PROXY  echo [net] Снимаю HTTP_PROXY=%HTTP_PROXY%
  if defined ALL_PROXY   echo [net] Снимаю ALL_PROXY=%ALL_PROXY%
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

rem --- настройки (можно править) ---
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b
set VIU_LLM_TIMEOUT=600
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
rem Blender (если «Принять asset» не находит сам — раскомментируй и поправь путь):
rem set VIU_BLENDER_EXE=C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe
rem Telegram (токен от @BotFather — см. docs/TELEGRAM.md):
rem set VIU_TELEGRAM_TOKEN=123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
rem Handoff Viu -> Cursor (push docs/CURSOR_HANDOFF.md):
rem set VIU_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
rem Пробуждение Viu по таймеру (минуты; 0 = выкл):
rem set VIU_HEARTBEAT_MIN=30
rem Тихие часы — не слать heartbeat/пуши (локальное время ПК):
set VIU_QUIET_HOURS=0-7
rem Температура «живой речи» в reflect (0.7–0.95; без этого qwen отвечает сухо):
set VIU_REFLECT_TEMPERATURE=0.88
rem ---------------------------------

echo.
echo   Готовлю Вью... (это окно закроется само)
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден.
  echo Установи Python 3.10+ с https://www.python.org/downloads/
  echo и поставь галочку "Add python.exe to PATH".
  goto :fail
)

echo [1/2] Проверяю обновления...
if exist "%~dp0bootstrap_update.py" python bootstrap_update.py --auto

echo [1b/2] Файл настроек .env...
if not exist "%~dp0.env" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%~dp0.env" >nul

echo [2/2] Готовлю пакет...
python -m pip install -e . -q --proxy=""
if errorlevel 1 (
  echo [net] Повтор без скачивания setuptools (--no-build-isolation)...
  python -m pip install -e . -q --proxy="" --no-build-isolation
)
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить пакет Viu.
  echo.
  echo Если в ошибке было 127.0.0.1:PORT — у тебя в системе прописан
  echo прокси ^(Clash/VPN^), который сейчас выключен. Выключи proxy в
  echo параметрах Windows или закрой старые переменные HTTP_PROXY.
  echo Быстрый обход уже в этом Viu.cmd; обнови файлы и запусти снова.
  goto :fail
)

rem Запускаем окно БЕЗ консоли (pythonw) и сразу выходим — чёрное окно не висит.
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0run_gui.pyw"
) else (
  start "" python "%~dp0run_gui.pyw"
)
exit /b 0

:fail
echo.
echo Нажми любую клавишу, чтобы закрыть окно...
pause >nul
exit /b 1
