@echo off
rem Odna komanda dlya pervoj ustanovki ili obnovleniya Viu (bez git).
chcp 65001 >nul
cd /d "%~dp0"
title Viu — zagruzka i obnovlenie

echo ============================================
echo   Viu — avtoobnovlenie s GitHub
echo ============================================
echo.

set PYTHONUTF8=1
set PYTHONPATH=%~dp0

where python >nul 2>&1
if errorlevel 1 (
  echo Python ne najden. Ustanovi s https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist "%~dp0bootstrap_update.py" (
  echo Zagruzhayu avtoapdater...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Shadowsector/Viu/cursor/viu-agent-core-65c2/bootstrap_update.py' -OutFile '%~dp0bootstrap_update.py' -UseBasicParsing } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo Ne udalos skachat bootstrap_update.py — prover internet.
    pause
    exit /b 1
  )
)

python "%~dp0bootstrap_update.py" --apply --launch
if errorlevel 1 pause
exit /b 0
