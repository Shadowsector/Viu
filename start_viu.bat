@echo off
rem Единственная точка входа Вью — графическое окно без чёрной консоли.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

rem ==== Настройки (можно править) ====
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b

set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_AUTO_UPDATE=1
rem ===================================

rem pythonw = без окна терминала; fallback на python
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw -m viu gui
) else (
  start "" python -m viu gui
)
exit /b 0
