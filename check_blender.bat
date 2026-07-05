@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Viu - proverka Blender
echo === blender_info (chto Vyu vidit v scene) ===
python -m viu tool blender_info
echo.
echo === rig_check (sverka skeleta so standartom) ===
python -m viu tool rig_check
echo.
echo Gotovo. Skopiruy vyvod vyshe i prishli ego.
pause
