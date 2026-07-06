@echo off
rem Viu — zapusk s avtoobnovleniem (bez git, bez ruchnogo zip).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%~dp0

rem ==== Nastroyki ====
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_AUTO_UPDATE=1
rem ===================

where python >nul 2>&1
if errorlevel 1 (
  echo Python ne najden. Ustanovi Python 3.10+ s python.org
  pause
  exit /b 1
)

rem --- Avtoapdater (skachivaet bootstrap s GitHub, esli net) ---
if not exist "%~dp0bootstrap_update.py" (
  echo [Viu] Pervyj zapusk: zagruzhayu avtoapdater...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Shadowsector/Viu/cursor/viu-agent-core-65c2/bootstrap_update.py' -OutFile '%~dp0bootstrap_update.py' -UseBasicParsing } catch { exit 1 }" 2>nul
)

if exist "%~dp0bootstrap_update.py" if "%VIU_AUTO_UPDATE%"=="1" (
  python "%~dp0bootstrap_update.py" --auto
)

rem --- GUI ---
if exist "%~dp0start_viu.vbs" (
  wscript //nologo "%~dp0start_viu.vbs"
  exit /b 0
)

if exist "%~dp0run_gui.pyw" (
  where pythonw >nul 2>&1
  if %errorlevel%==0 (
    start "" pythonw "%~dp0run_gui.pyw"
  ) else (
    start "" python "%~dp0run_gui.pyw"
  )
  exit /b 0
)

python -c "import sys; sys.path.insert(0, r'%~dp0'); import viu.gui" 2>"%~dp0viu_startup.log"
if errorlevel 1 (
  echo Oshibka zapuska. Sm. viu_startup.log
  echo Ili zapusti: get_viu.bat
  type "%~dp0viu_startup.log"
  pause
  exit /b 1
)
start "" pythonw -m viu gui
exit /b 0
