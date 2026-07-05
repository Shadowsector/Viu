@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Viu - console
echo ============================================================
echo   Konsol otkryta v papke Vyu (%~dp0)
echo   Mozhno srazu pisat komandy, naprimer:
echo     python -m viu tool blender_info
echo     python -m viu tool rig_check
echo     python -m viu tools
echo ============================================================
echo.
cmd /k
