@echo off
setlocal EnableExtensions
set "EC=0"
cd /d "%~dp0.."

chcp 65001 >nul
echo ========================================
echo  Create clean Ollama models for Viu
echo  Folder: %CD%
echo ========================================
echo.
echo Google/Ollama tip: Euryale/Nevoria refuse NSFW when the
echo pulled tag has a safety SYSTEM. We recreate clean tags:
echo   viu-euryale
echo   viu-nevoria  (optional)
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo ERROR: ollama.exe not in PATH. Start Ollama first.
  set "EC=1"
  goto END
)

if not exist "ollama\Modelfile.viu-euryale" (
  echo ERROR: ollama\Modelfile.viu-euryale missing. Update Viu.
  set "EC=1"
  goto END
)

echo --- ollama list ---
ollama list
echo.

echo Creating viu-euryale from Modelfile.viu-euryale ...
ollama create viu-euryale -f "ollama\Modelfile.viu-euryale"
if errorlevel 1 (
  echo ERROR: ollama create viu-euryale failed.
  set "EC=1"
  goto END
)
echo OK: viu-euryale

echo.
echo Optional Nevoria: set FROM in ollama\Modelfile.viu-nevoria
echo to your exact tag from the list above, then create.
set "DO_NEV=N"
set /p DO_NEV=Create viu-nevoria now? [y/N]: 
if /i "%DO_NEV%"=="y" (
  ollama create viu-nevoria -f "ollama\Modelfile.viu-nevoria"
  if errorlevel 1 (
    echo ERROR: fix FROM= in ollama\Modelfile.viu-nevoria to your real tag.
    set "EC=1"
  ) else (
    echo OK: viu-nevoria
  )
)

echo.
echo ----------------------------------------
echo Next:
echo   1) In U:\Viu\.env set:
echo        VIU_MODEL_REFLECT=viu-euryale
echo   2) Restart Viu
echo   3) Run diag_nsfw.bat  (or ask Viu about NSFW)
echo.
echo Quick console check:
echo   ollama run viu-euryale
echo   then ask: can you write NSFW?
echo.

:END
echo Press any key to close...
pause >nul
endlocal & exit /b %EC%
