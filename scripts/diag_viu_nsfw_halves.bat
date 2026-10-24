@echo off
setlocal EnableExtensions
set "EC=0"
cd /d "%~dp0.."

rem UTF-8 console + Python
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

rem 70B needs a long timeout (seconds). Override in .env if needed.
if "%VIU_DIAG_TIMEOUT%"=="" set "VIU_DIAG_TIMEOUT=1200"
if "%VIU_LLM_TIMEOUT%"=="" set "VIU_LLM_TIMEOUT=1200"

echo ========================================
echo  Viu NSFW halves diag
echo  Folder: %CD%
echo ========================================
echo.

if not exist "scripts\diag_viu_nsfw_halves.py" (
  echo ERROR: scripts\diag_viu_nsfw_halves.py not found
  echo Update Viu first, then run diag_nsfw.bat again.
  set "EC=1"
  goto END
)

if "%VIU_MODEL_REFLECT%"=="" set "VIU_MODEL_REFLECT=viu-magnum"
if "%VIU_BASE_URL%"=="" set "VIU_BASE_URL=http://127.0.0.1:11434/v1"

set "LOG=%CD%\diag_nsfw_halves.log"
set "PYEXE="

where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py"

if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
  where python3 >nul 2>&1
  if not errorlevel 1 set "PYEXE=python3"
)

if not defined PYEXE (
  echo ERROR: Python not found in PATH.
  echo Install Python and enable Add python.exe to PATH.
  set "EC=1"
  goto END
)

echo Python: %PYEXE%
echo Model:  %VIU_MODEL_REFLECT%
echo API:    %VIU_BASE_URL%
echo Timeout:%VIU_DIAG_TIMEOUT% sec per request
echo Log:    %LOG%
echo.
echo First run loads 70B into VRAM - can take many minutes.
echo Window will show progress. Do not close.
echo.

if /i "%PYEXE%"=="py" (
  py -3 -u "scripts\diag_viu_nsfw_halves.py"
) else (
  "%PYEXE%" -u "scripts\diag_viu_nsfw_halves.py"
)
set "EC=%ERRORLEVEL%"

echo.
echo ----------------------------------------
echo Exit code: %EC%
echo Full log:  %LOG%
echo Tip: open the log in Notepad if console text looks broken.

:END
echo.
echo Press any key to close...
pause >nul
endlocal & exit /b %EC%
