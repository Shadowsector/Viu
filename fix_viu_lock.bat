@echo off
rem Free zombie lock on port 47615 if Viu window is gone but launch says already_running.
rem Also reset off-screen window_geometry (left monitor) in .viu\runtime.json.
chcp 65001 >nul
cd /d "%~dp0"
echo Checking port 47615...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c = Get-NetTCPConnection -LocalPort 47615 -ErrorAction SilentlyContinue; if (-not $c) { Write-Host 'Port free - nothing to kill.'; exit 0 }; $c | ForEach-Object { Write-Host ('Killing PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Host Done."
echo.
echo Reset off-screen window position (if any)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Join-Path '%~dp0' '.viu\runtime.json'; if (-not (Test-Path $p)) { Write-Host 'No runtime.json'; exit 0 }; try { $j = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json; $g = [string]$j.window_geometry; if ($g -match '^[+-]' -or $g -match 'x\d+[+-]-') { $j.window_geometry = '1200x840+80+60'; ($j | ConvertTo-Json -Compress) | Set-Content $p -Encoding UTF8; Write-Host ('Was: ' + $g + ' -> 1200x840+80+60') } else { Write-Host ('Geometry OK: ' + $g) } } catch { Write-Host ('runtime.json: ' + $_) }"
echo.
echo Now run Viu.cmd (not go.bat if you need update).
pause
