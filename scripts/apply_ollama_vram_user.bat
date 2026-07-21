@echo off
rem Прописать OLLAMA_MAX_VRAM в профиль Windows (для Ollama в трее).
rem Запусти от Дена, потом выйди из Ollama и запусти снова.
cd /d "%~dp0.."
set "GB=10"
if exist ".env" for /f "usebackq tokens=1,* delims==" %%a in (`findstr /i "^VIU_LAB_VRAM_GB=" ".env"`) do set "GB=%%b"
set /a BYTES=%GB%*1024*1024*1024
echo VIU_LAB_VRAM_GB=%GB%  -^>  OLLAMA_MAX_VRAM=%BYTES% bytes
setx OLLAMA_MAX_VRAM %BYTES%
echo.
echo Готово. Перезапусти Ollama из трея (Quit -^> снова открыть).
pause
