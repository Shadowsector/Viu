@echo off
rem Единственная точка входа Вью — графическое окно (без чёрной консоли).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%~dp0

rem ==== Настройки (можно править) ====
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b

set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_AUTO_UPDATE=1
rem ===================================

rem Быстрая проверка перед запуском (ошибка — не исчезаем молча)
python -c "import sys; sys.path.insert(0, r'%~dp0'); import viu.gui" 2>"%~dp0viu_startup.log"
if errorlevel 1 (
  echo.
  echo [Viu] Ne udalos zapustit GUI. Oshibka:
  type "%~dp0viu_startup.log"
  echo.
  echo Esli Python ne najden — ustanovi Python 3.10+ s python.org
  echo Ili: pip install -e .
  pause
  exit /b 1
)

rem VBS = bez melkaniya chernogo okna
if exist "%~dp0start_viu.vbs" (
  wscript //nologo "%~dp0start_viu.vbs"
  exit /b 0
)

rem Zapasnoj put
start "" py -3w "%~dp0run_gui.pyw"
exit /b 0
