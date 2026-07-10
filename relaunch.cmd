@echo off
rem Перезапуск Viu после обновления (вызывается из окна Вью).
chcp 65001 >nul
cd /d "%~dp0"
rem Ждём, пока старый процесс освободит порт (single-instance).
ping -n 3 127.0.0.1 >nul
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0run_gui.pyw"
) else (
  start "" python "%~dp0run_gui.pyw"
)
exit /b 0
