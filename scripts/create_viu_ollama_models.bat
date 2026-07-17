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
echo Recommended daily set:
echo   viu-cydonia   24B story/NSFW/chat  (pull Cydonia first)
echo   + qwen2.5:32b-instruct   work
echo   + qwen2.5-coder:14b      code (fast)
echo.
echo Also builds:
echo   viu-magnum viu-euryale viu-nevoria viu-dolphin viu-abliterated
echo.
echo Tip: 70B crawling = VRAM swap. Run: ollama stop
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

call :MAKE viu-cydonia      ollama\Modelfile.viu-cydonia
call :MAKE viu-magnum       ollama\Modelfile.viu-magnum
call :MAKE viu-euryale      ollama\Modelfile.viu-euryale
call :MAKE viu-nevoria      ollama\Modelfile.viu-nevoria
call :MAKE viu-dolphin      ollama\Modelfile.viu-dolphin
call :MAKE viu-abliterated  ollama\Modelfile.viu-abliterated

echo.
echo ----------------------------------------
echo Recommended .env:
echo   VIU_MODEL_REFLECT=viu-cydonia
echo   VIU_MODEL_WORK=qwen2.5:32b-instruct
echo   VIU_MODEL_CODE=qwen2.5-coder:14b
echo.
echo Pull Cydonia if missing:
echo   ollama pull moophlo/Cydonia-24B-v4.3-GGUF:Q4_K_M
echo Then re-run this bat.
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
  echo FAIL: %TAG%  (base model not pulled? check FROM in Modelfile)
  set "EC=1"
) else (
  echo OK: %TAG%
)
goto :eof
