@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Viu - Anabarra
cd /d "%~dp0"

rem ==== Nastroyki Vyu (mozhno pravit) ====
rem Lokalnaya Ollama v OpenAI-sovmestimom rezhime:
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b

rem Put k Blender dlya chteniya .blend v fone (raskommentiruy i popravь):
rem set VIU_BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.1\blender.exe

rem Put k Unity-proektu Anabarra:
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
rem =======================================

echo.
echo   Zapusk Vyu... (Ollama dolzhna byt zapushchena)
echo.

rem Graficheskoe okno. Dlya konsoli zameni "gui" na "chat".
python -m viu gui
if errorlevel 1 (
  echo.
  echo Ne udalos otkryt okno, probuyu konsolnyy rezhim...
  python -m viu chat
)
pause
