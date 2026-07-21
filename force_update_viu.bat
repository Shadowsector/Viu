@echo off
rem Принудительное обновление Viu с GitHub (zip) — когда «Обновить Вью» врёт.
chcp 65001 >nul
cd /d "%~dp0"
title Viu — force update
set PYTHONUTF8=1

echo.
echo   Принудительное обновление Viu
echo   Ветка: %VIU_UPDATE_BRANCH%
echo   (по умолчанию cursor/viu-agent-core-65c2)
echo.

if not defined VIU_UPDATE_BRANCH set "VIU_UPDATE_BRANCH=cursor/viu-agent-core-65c2"

if /i not "%VIU_KEEP_PROXY%"=="1" (
  set "HTTP_PROXY="
  set "HTTPS_PROXY="
  set "ALL_PROXY="
  set "NO_PROXY=*"
)

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python не найден.
  pause
  exit /b 1
)

echo [1/2] bootstrap_update.py --apply
python bootstrap_update.py --apply
if errorlevel 1 (
  echo bootstrap failed — пробую python -m viu update --apply --force
  python -m viu update --apply --force
  if errorlevel 1 (
    echo Оба способа не сработали — см. вывод выше
    pause
    exit /b 1
  )
)

echo [2/2] pip install -e .
python -m pip install -e . -q --proxy="" --disable-pip-version-check
if errorlevel 1 (
  python -m pip install -e . -q --proxy="" --no-build-isolation --disable-pip-version-check
)

echo.
echo Готово. Закрой все окна Вью и запусти Viu.cmd снова.
echo Проверка: type viu\package_sha.txt
echo.
pause
