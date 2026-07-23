@echo off
rem Перезапуск Viu БЕЗ обновления (как было до Viu.cmd).
rem Для апдейта с GitHub: Viu.cmd  или  force_update_viu.bat
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
echo.
echo [relaunch] Только GUI — GitHub не трогаю.
for /f "delims=" %%V in ('python -c "from viu.updater import version_label,running_sha; s=running_sha() or ''; print('  Версия:', version_label(), s[:7] if s else '?')" 2^>nul') do echo %%V
echo.
rem Ждём, пока старый процесс освободит порт (single-instance).
ping -n 3 127.0.0.1 >nul
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0run_gui.pyw"
) else (
  start "" python "%~dp0run_gui.pyw"
)
exit /b 0
