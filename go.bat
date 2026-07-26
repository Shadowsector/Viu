@echo off
rem Запуск Вью без GitHub/pip — если Viu.cmd молчит или зависает.
rem Полный апдейт: Viu.cmd  (не quick!)  или  force_update_viu.bat / кнопка «Обновить Вью».
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден в PATH.
  pause
  exit /b 1
)
rem pythonw без чёрного окна; отладка: set VIU_SHOW_CONSOLE=1
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
