@echo off
rem Obnovlenie tolko esli repozitorij publichnyj ili est VIU_GITHUB_TOKEN
cd /d "%~dp0"
set PYTHONPATH=%~dp0
if not exist bootstrap_update.py (
  echo bootstrap_update.py dolzhen byt v papke Viu iz zip.
  pause
  exit /b 1
)
python bootstrap_update.py --apply
if errorlevel 1 pause
exit /b 0
