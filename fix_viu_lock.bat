@echo off
rem Free zombie lock on port 47615 if Viu window is gone but launch says already_running.
rem Also reset off-screen window_geometry (left monitor) in .viu\runtime.json.
chcp 65001 >nul
cd /d "%~dp0"
echo Checking port 47615...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c = Get-NetTCPConnection -LocalPort 47615 -ErrorAction SilentlyContinue; if (-not $c) { Write-Host 'Port free - nothing to kill.'; exit 0 }; $c | ForEach-Object { Write-Host ('Killing PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Host Done."
echo.
echo Window geometry: left-monitor negative X is OK (Viu keeps it if monitor is on).
echo Only reset manually if the window is truly gone — delete window_geometry in .viu\runtime.json
echo or run: python -c "from viu.runtime_settings import sanitize_window_geometry; print('ok')"
echo.
echo Now run Viu.cmd (not go.bat if you need update).
pause
