@echo off
rem Pervaya ustanovka Viu (esli net git).
chcp 65001 >nul
cd /d "%~dp0"
title Viu — ustanovka

echo ============================================
echo   Viu — ustanovka
echo ============================================
echo.
echo Variant A (rekomenduetsya): git
echo   git clone -b cursor/viu-agent-core-65c2 ^
echo     https://github.com/Shadowsector/Viu.git U:\Viu
echo.
echo Variant B: uzhe skachal zip — v etoj papke:
echo   1. update_viu.bat
echo   2. pip install -e .
echo   3. start_viu.bat
echo.
pause
