@echo off
rem Полная диагностика — окно остаётся открытым.
chcp 65001 >nul
cd /d "%~dp0"
title Viu — диагностика
set PYTHONUTF8=1
set PYTHONPATH=%~dp0

echo ============================================
echo   Viu — диагностика
echo ============================================
echo.

echo --- Python ---
where python 2>nul || echo python НЕ в PATH
python --version 2>nul || echo python не запускается

echo.
echo --- tkinter ---
python -c "import tkinter; print('tkinter OK')" 2>nul || echo tkinter ОШИБКА

echo.
echo --- import viu ---
python -c "import sys; sys.path.insert(0, r'%~dp0'); import viu; print('viu OK', viu.__file__)" 2>&1

echo.
echo --- pip install -e . ---
python -m pip install -e . 2>&1

echo.
echo --- run_gui ---
python run_gui.pyw 2>&1
echo exit code: %errorlevel%

echo.
if exist viu_startup.log (
  echo --- viu_startup.log ---
  type viu_startup.log
)

echo.
echo ============================================
pause
