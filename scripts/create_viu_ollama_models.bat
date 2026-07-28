@echo off
setlocal EnableExtensions
set "EC=0"
cd /d "%~dp0.."

rem Slim NSFW set only. Never recreate 70B wrappers even if old Modelfiles linger.
set "VIU_WRAPPER_SET=slim-cydonia-magnum32-commandr-qwen32"

chcp 65001 >nul
echo ========================================
echo  Create NSFW-clean Ollama tags for Viu
echo  Folder: %CD%
echo  Set:    %VIU_WRAPPER_SET%
echo ========================================
echo.
echo Builds ONLY:
echo   viu-cydonia     Cydonia 24B     reflect / chat / ERP
echo   viu-magnum      Magnum 32B      literary NSFW
echo   viu-command-r   Command R 35B   GDD / quests / tables
echo   viu-qwen32      Qwen 2.5 32B    work + design
echo.
echo NEVER builds: viu-euryale / viu-nevoria / viu-dolphin / viu-abliterated
echo Not wrapped:  qwen2.5-coder:14b , llava
echo Tip: jailbreak — правь ollama\Modelfile.viu-* БЕЗ .example, см. ollama\README.txt
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo ERROR: ollama.exe not in PATH.
  set "EC=1"
  goto END
)

if not exist "ollama\Modelfile.viu-cydonia" (
  if exist "ollama\Modelfile.viu-cydonia.example" (
    copy /y "ollama\Modelfile.viu-cydonia.example" "ollama\Modelfile.viu-cydonia" >nul
    echo Seeded ollama\Modelfile.viu-cydonia from .example ^(локальный файл, не в git^).
  ) else (
    echo ERROR: Modelfiles missing. Update Viu first ^(pull latest / zip^).
    set "EC=1"
    goto END
  )
)

call :SEED_IF_MISSING viu-magnum
call :SEED_IF_MISSING viu-command-r
call :SEED_IF_MISSING viu-qwen32

rem If an old Viu tree left 70B Modelfiles on disk — delete them so nothing can recreate.
call :SCRUB_OLD ollama\Modelfile.viu-euryale
call :SCRUB_OLD ollama\Modelfile.viu-nevoria
call :SCRUB_OLD ollama\Modelfile.viu-dolphin
call :SCRUB_OLD ollama\Modelfile.viu-abliterated

echo --- ollama list ---
ollama list
echo.

call :MAKE viu-cydonia     ollama\Modelfile.viu-cydonia
call :MAKE viu-magnum      ollama\Modelfile.viu-magnum
call :MAKE viu-command-r   ollama\Modelfile.viu-command-r
call :MAKE viu-qwen32      ollama\Modelfile.viu-qwen32

echo.
echo ----------------------------------------
echo Done. If you still see "viu-euryale" in the tip above — you ran an OLD bat.
echo Update Viu, then re-run this script from U:\Viu\scripts\
echo.
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

:SCRUB_OLD
if exist "%~1" (
  echo WARNING: stale %~1 found — deleting so 70B wrappers cannot be recreated.
  del /f /q "%~1" >nul 2>&1
)
goto :eof

:MAKE
set "TAG=%~1"
set "MF=%~2"
if /i "%TAG%"=="viu-euryale" goto :BLOCKED
if /i "%TAG%"=="viu-nevoria" goto :BLOCKED
if /i "%TAG%"=="viu-dolphin" goto :BLOCKED
if /i "%TAG%"=="viu-abliterated" goto :BLOCKED
if not exist "%MF%" (
  echo SKIP %TAG% - no %MF%
  goto :eof
)
echo.
echo Creating %TAG% from %MF% ...
for %%F in ("%MF%") do echo   файл: %%~fF
ollama create %TAG% -f "%MF%"
if errorlevel 1 (
  echo FAIL: %TAG%  ^(base not pulled? check FROM in Modelfile^)
  set "EC=1"
) else (
  echo OK: %TAG%
)
goto :eof

:BLOCKED
echo BLOCKED: refusing to create %TAG% ^(70B set retired^).
set "EC=1"
goto :eof

:SEED_IF_MISSING
set "TAG=%~1"
set "MF=ollama\Modelfile.%TAG%"
set "EX=%MF%.example"
if exist "%MF%" goto :eof
if not exist "%EX%" goto :eof
copy /y "%EX%" "%MF%" >nul
echo Seeded %MF% from .example ^(локальный файл, не в git^).
goto :eof
