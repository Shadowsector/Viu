@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Sozdayu yarlyk "Vyu" na rabochem stole...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
pause
