@echo off
rem ============================================================
rem  VIU — единственный файл для запуска (окно НЕ исчезает при ошибке)
rem  Двойной клик сюда. Остальные .bat — устарели.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title Viu — Anabarra
set PYTHONUTF8=1
set PYTHONPATH=%~dp0

rem --- настройки ---
set VIU_PROVIDER=openai
set VIU_BASE_URL=http://localhost:11434/v1
set VIU_API_KEY=ollama
set VIU_MODEL=qwen2.5-coder:14b
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_ANIM_STAGING=U:\Anabarra\Animations
set VIU_AUTO_UPDATE=0
rem VIU_AUTO_UPDATE=1 только если репозиторий публичный или задан VIU_GITHUB_TOKEN

echo.
echo   Viu — запуск
echo   Папка: %~dp0
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден.
  echo Установи Python 3.10+ с https://www.python.org/downloads/
  echo При установке отметь "Add python.exe to PATH" и tcl/tk.
  goto :fail
)

echo [1/3] Python:
python --version

echo.
echo [2/3] Установка пакета Viu ^(pip install -e .^)...
python -m pip install -e . -q
if errorlevel 1 (
  echo [ОШИБКА] pip install не удался.
  goto :fail
)

echo.
echo [3/3] Запуск окна Viu...
python "%~dp0run_gui.pyw"
if errorlevel 1 goto :showlog

echo.
echo Viu закрыт.
pause
exit /b 0

:showlog
echo.
echo [ОШИБКА] Не удалось открыть Viu.
if exist "%~dp0viu_startup.log" (
  echo --- viu_startup.log ---
  type "%~dp0viu_startup.log"
) else (
  echo Лог пуст. Проверь: python -c "import tkinter"
)
goto :fail

:fail
echo.
echo Нажми любую клавишу для выхода...
pause >nul
exit /b 1
