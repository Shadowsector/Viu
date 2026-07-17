@echo off
setlocal EnableExtensions
set "EC=0"
cd /d "%~dp0.."

chcp 65001 >nul
echo ========================================
echo  Create NSFW-clean Ollama tags for Viu
echo  Folder: %CD%
echo ========================================
echo.
echo Builds:
echo   viu-cydonia     Cydonia 24B     reflect / chat / ERP
echo   viu-magnum      Magnum 32B      literary NSFW
echo   viu-command-r   Command R 35B   GDD / quests / tables
echo   viu-qwen32      Qwen 2.5 32B    work + design
echo.
echo Not wrapped: qwen2.5-coder:14b (code), llava (vision only).
echo Tip: ollama stop before switching heavy models.
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo ERROR: ollama.exe not in PATH.
  set "EC=1"
  goto END
)

if not exist "ollama\Modelfile.viu-cydonia" (
  echo ERROR: Modelfiles missing. Update Viu first.
  set "EC=1"
  goto END
)

echo --- ollama list ---
ollama list
echo.

call :MAKE viu-cydonia     ollama\Modelfile.viu-cydonia
call :MAKE viu-magnum      ollama\Modelfile.viu-magnum
call :MAKE viu-command-r   ollama\Modelfile.viu-command-r
call :MAKE viu-qwen32      ollama\Modelfile.viu-qwen32

echo.
echo ----------------------------------------
echo Recommended .env:
echo   VIU_MODEL_REFLECT=viu-cydonia
echo   VIU_MODEL_WORK=viu-qwen32
echo   VIU_MODEL_CODE=qwen2.5-coder:14b
echo Optional GDD nights: VIU_MODEL_REFLECT=viu-command-r
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
  echo FAIL: %TAG%  (base not pulled? check FROM in Modelfile)
  set "EC=1"
) else (
  echo OK: %TAG%
)
goto :eof
