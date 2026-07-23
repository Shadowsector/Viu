@echo off
rem Запуск Вью без GitHub/pip — если Viu.cmd молчит или зависает.
rem Полный апдейт: Viu.cmd quick  или  force_update_viu.bat
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Viu
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
echo [go] Запуск run_gui.pyw (без bootstrap/pip)...
python "%~dp0run_gui.pyw"
exit /b %errorlevel%
