@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title Viu - proverka Blender
set "REPORT=%~dp0blender_report.txt"

echo === blender_info (chto Vyu vidit v scene) ===> "%REPORT%"
python -m viu tool blender_info >> "%REPORT%" 2>&1
echo.>> "%REPORT%"
echo === rig_check (sverka skeleta so standartom) ===>> "%REPORT%"
python -m viu tool rig_check >> "%REPORT%" 2>&1

type "%REPORT%"
echo.
echo ============================================================
echo   Otchet sohranen v fayl:
echo   %REPORT%
echo   Prishli mne etot fayl (ili skopiruy tekst vyshe).
echo ============================================================
pause
