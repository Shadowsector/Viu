@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title Viu - proverka Unity
set "REPORT=%~dp0unity_report.txt"

if not "%VIU_UNITY_PROJECT%"=="" (
  set "UNITY_PROJ=%VIU_UNITY_PROJECT%"
) else (
  set "UNITY_PROJ=U:\Anabarra\Unity\Anabarra"
)

echo === unity_report ===> "%REPORT%"
echo Unity project: %UNITY_PROJ%>> "%REPORT%"
echo.>> "%REPORT%"
set VIU_UNITY_PROJECT=%UNITY_PROJ%
python -m viu tool unity_report >> "%REPORT%" 2>&1

type "%REPORT%"
echo.
echo ============================================================
echo   Otchet: %REPORT%
echo   Esli proekt ne tam — zadaj peremenную:
echo   set VIU_UNITY_PROJECT=U:\Anabarra\Unity\MyProject
echo ============================================================
pause
