@echo off
rem ============================================================
rem   VIU — запусти двойным кликом. Это единственный нужный файл.
rem   Окно остаётся открытым, если что-то пошло не так.
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
rem ---------------------------------

echo.
echo   Запускаю Вью из %~dp0
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден.
  echo Установи Python 3.10+ с https://www.python.org/downloads/
  echo и поставь галочку "Add python.exe to PATH".
  goto :fail
)

echo [1/3] Проверяю обновления с GitHub...
if exist "%~dp0bootstrap_update.py" (
  python bootstrap_update.py --auto
) else (
  echo   ^(bootstrap_update.py нет — пропускаю^)
)

echo.
echo [2/3] Готовлю Вью...
python -m pip install -e . -q
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить пакет Viu.
  goto :fail
)

echo.
echo [3/3] Открываю окно Вью...
python run_gui.pyw
if errorlevel 1 goto :showlog

echo.
echo Вью закрыта. До встречи!
timeout /t 3 >nul
exit /b 0

:showlog
echo.
echo [ОШИБКА] Окно Вью не открылось. Подробности:
if exist "%~dp0viu_startup.log" (
  echo ------------------------------------------------------------
  type "%~dp0viu_startup.log"
  echo ------------------------------------------------------------
) else (
  echo Лог пуст. Проверь tkinter:  python -c "import tkinter"
)

:fail
echo.
echo Нажми любую клавишу, чтобы закрыть окно...
pause >nul
exit /b 1
