@echo off
rem Запустить ComfyUI :8188 (install если нет)
chcp 65001 >nul
cd /d "%~dp0"
python -m viu tool comfy_ensure
if errorlevel 1 pause
exit /b %ERRORLEVEL%
