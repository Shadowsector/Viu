@echo off
rem Free zombie lock on port 47615 if Viu window is gone but launch says already_running
chcp 65001 >nul
cd /d "%~dp0"
echo Checking port 47615...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c = Get-NetTCPConnection -LocalPort 47615 -ErrorAction SilentlyContinue; if (-not $c) { Write-Host 'Port free - nothing to kill.'; exit 0 }; $c | ForEach-Object { Write-Host ('Killing PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Host Done."
echo.
echo Now run Viu.cmd again.
pause
