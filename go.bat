@echo off
rem Запуск Вью без GitHub/pip — если Viu.cmd молчит или зависает.
rem Полный апдейт: Viu.cmd quick  или  force_update_viu.bat
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Viu
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
echo [go] Запуск run_gui.pyw (без bootstrap/pip)...
where pythonw >nul 2>&1
if errorlevel 1 (
  start "" python "%~dp0run_gui.pyw"
) else (
  start "" pythonw "%~dp0run_gui.pyw"
)
exit /b 0
