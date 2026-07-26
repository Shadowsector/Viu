@echo off
rem Перезапуск Viu БЕЗ обновления (как было до Viu.cmd).
rem Для апдейта с GitHub: Viu.cmd  или  force_update_viu.bat
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
rem Ждём, пока старый процесс освободит порт (single-instance).
ping -n 4 127.0.0.1 >nul
rem По умолчанию pythonw — без чёрной консоли. Отладка: set VIU_SHOW_CONSOLE=1
where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден в PATH.
  exit /b 1
)
if defined VIU_SHOW_CONSOLE (
  start "" python "%~dp0run_gui.pyw"
  exit /b 0
)
where pythonw >nul 2>&1
if errorlevel 1 (
  start "" python "%~dp0run_gui.pyw"
) else (
  start "" pythonw "%~dp0run_gui.pyw"
)
exit /b 0
