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
echo Builds NSFW-clean tags (rewrites Ollama SYSTEM):
echo   viu-magnum       - fluffy/magnum-v3-34b   FAST chat
echo   viu-euryale      - nchapman euryale 70b
echo   viu-nevoria      - ScrambieBambie Nevoria 70b
echo   viu-dolphin      - dolphin-llama3:70b
echo   viu-abliterated  - huihui llama3.3 abliterated 70b
echo.
echo Tip: 70B crawling 1 letter / 5s = VRAM swap. Run:
echo   ollama stop
echo then use ONE model. For speed try viu-magnum (34B).
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo ERROR: ollama.exe not in PATH.
  set "EC=1"
  goto END
)

if not exist "ollama\Modelfile.viu-euryale" (
  echo ERROR: ollama\Modelfile.* missing. Update Viu first.
  set "EC=1"
  goto END
)

echo --- ollama list ---
ollama list
echo.

call :MAKE viu-magnum       ollama\Modelfile.viu-magnum
call :MAKE viu-euryale      ollama\Modelfile.viu-euryale
call :MAKE viu-nevoria      ollama\Modelfile.viu-nevoria
call :MAKE viu-dolphin      ollama\Modelfile.viu-dolphin
call :MAKE viu-abliterated  ollama\Modelfile.viu-abliterated

echo.
echo ----------------------------------------
echo In U:\Viu\.env set ONE of:
echo   VIU_MODEL_REFLECT=viu-magnum
echo   VIU_MODEL_REFLECT=viu-abliterated
echo   VIU_MODEL_REFLECT=viu-dolphin
echo   VIU_MODEL_REFLECT=viu-euryale
echo   VIU_MODEL_REFLECT=viu-nevoria
echo.
echo Then restart Viu. Quick test:
echo   ollama stop
echo   ollama run viu-magnum
echo   Ask: can you write NSFW?
echo.

:END
echo Press any key to close...
pause >nul
endlocal & exit /b %EC%

:MAKE
set "TAG=%~1"
set "MF=%~2"
if not exist "%MF%" (
  echo SKIP %TAG% - no %MF%
  goto :eof
)
echo.
echo Creating %TAG% from %MF% ...
ollama create %TAG% -f "%MF%"
if errorlevel 1 (
  echo FAIL: %TAG%  (base model not pulled yet? check FROM in Modelfile)
  set "EC=1"
) else (
  echo OK: %TAG%
)
goto :eof
