@echo off
setlocal EnableExtensions
set "EC=0"
cd /d "%~dp0.."

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

if "%VIU_MODEL_REFLECT%"=="" set "VIU_MODEL_REFLECT=nchapman/l3.3-70b-euryale-v2.3"
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
  echo Or run from cmd with full path to python.exe
  set "EC=1"
  goto END
)

echo Python: %PYEXE%
echo Model:  %VIU_MODEL_REFLECT%
echo API:    %VIU_BASE_URL%
echo Log:    %LOG%
echo.
echo Wait - large models are slow...
echo.

if /i "%PYEXE%"=="py" (
  py -3 "scripts\diag_viu_nsfw_halves.py" > "%LOG%" 2>&1
) else (
  "%PYEXE%" "scripts\diag_viu_nsfw_halves.py" > "%LOG%" 2>&1
)
set "EC=%ERRORLEVEL%"

echo.
type "%LOG%"
echo.
echo ----------------------------------------
echo Exit code: %EC%
echo Full log:  %LOG%

:END
echo.
echo Press any key to close...
pause >nul
endlocal & exit /b %EC%
