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

rem --- настройки (можно править) ---
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
rem Blender (если «Принять asset» не находит сам — раскомментируй и поправь путь):
rem set VIU_BLENDER_EXE=C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe
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

echo [2/2] Готовлю пакет...
python -m pip install -e . -q
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить пакет Viu.
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
