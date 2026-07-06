@echo off
rem Obnovlenie Viu bez git — skachivaet zip s GitHub.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%~dp0
title Viu — obnovlenie

echo ============================================
echo   Viu — obnovlenie s GitHub (zip)
echo ============================================
echo.

python -m viu update --apply
if errorlevel 1 (
  echo.
  echo Oshibka. Prover internet i Python.
  pause
  exit /b 1
)

echo.
echo Gotovo! Zapusti start_viu.bat
pause
