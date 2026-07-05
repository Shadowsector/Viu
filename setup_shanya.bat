@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set VIU_NO_PAUSE=1
cd /d "%~dp0"
title Viu - init Unity Shanya

if not "%VIU_UNITY_PROJECT%"=="" (
  set "UNITY_PROJ=%VIU_UNITY_PROJECT%"
) else (
  set "UNITY_PROJ=U:\Anabarra\Unity\Anabarra"
)

echo Unity project: %UNITY_PROJ%
echo.
set VIU_UNITY_PROJECT=%UNITY_PROJ%

echo [1/2] unity_init_project...
python -m viu tool unity_init_project
echo.
echo [2/2] unity_report...
python -m viu tool unity_report
echo.
echo ============================================================
echo   Gotovo. Otkroj Unity, import FBX, Humanoid Configure,
echo   menu Viu - Setup Shanya (Idle), potom unity_verify
echo ============================================================
if "%VIU_NO_PAUSE%"=="1" goto :eof
pause
