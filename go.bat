@echo off
rem Запуск Вью без GitHub/pip — если Viu.cmd молчит или зависает.
rem Полный апдейт: Viu.cmd  (не quick!)  или  force_update_viu.bat / кнопка «Обновить Вью».
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Viu
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
echo [go] Запуск run_gui.pyw (без bootstrap/pip)...
where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден в PATH.
  pause
  exit /b 1
)
start "" python "%~dp0run_gui.pyw"
exit /b 0
