@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem Запускать двойным кликом или из Total Commander (Enter на этом .bat).
rem Окно НЕ закроется само — в конце Pause.
rem Лог также пишется в U:\Viu\diag_nsfw_halves.log

cd /d "%~dp0\.."
if not exist "scripts\diag_viu_nsfw_halves.py" (
  echo [ERR] Не вижу scripts\diag_viu_nsfw_halves.py
  echo Сейчас я в: %CD%
  echo Открой этот bat из папки Viu после обновления.
  goto :end
)

echo ========================================
echo  Viu NSFW halves diag
echo  Folder: %CD%
echo ========================================
echo.

rem Модель: из .env если уже задана, иначе дефолт Euryale
if "%VIU_MODEL_REFLECT%"=="" set "VIU_MODEL_REFLECT=nchapman/l3.3-70b-euryale-v2.3"
if "%VIU_BASE_URL%"=="" set "VIU_BASE_URL=http://127.0.0.1:11434/v1"

set "LOG=%CD%\diag_nsfw_halves.log"
echo Лог: %LOG%
echo.

rem Ищем python: py launcher, потом python, потом python3
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if "%PY%"=="" (
  where python >nul 2>&1 && set "PY=python"
)
if "%PY%"=="" (
  where python3 >nul 2>&1 && set "PY=python3"
)

if "%PY%"=="" (
  echo [ERR] Python не найден в PATH.
  echo.
  echo Варианты:
  echo   1^) Установи Python с python.org и галка "Add to PATH"
  echo   2^) Или в Total Commander открой cmd.exe ^(кнопка или Win+R -^> cmd^)
  echo      и напиши полный путь, например:
  echo      "C:\Users\ВАШЕ\AppData\Local\Programs\Python\Python312\python.exe" scripts\diag_viu_nsfw_halves.py
  echo.
  goto :end
)

echo Python: %PY%
echo Model:  %VIU_MODEL_REFLECT%
echo API:    %VIU_BASE_URL%
echo.
echo Жди — 70B думает долго ^(иногда 2-10 мин на половину^)...
echo.

%PY% scripts\diag_viu_nsfw_halves.py > "%LOG%" 2>&1
set "EC=%ERRORLEVEL%"
type "%LOG%"
echo.
echo ----------------------------------------
if "%EC%"=="0" (
  echo Готово. Код %EC%. Полный лог: %LOG%
) else (
  echo Закончено с кодом %EC%. Смотри лог: %LOG%
)

:end
echo.
echo Нажми любую клавишу, чтобы закрыть окно...
pause >nul
endlocal
exit /b %EC%
