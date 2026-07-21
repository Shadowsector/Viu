@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
chcp 65001 >nul
echo ========================================
echo  Abort heavy / obsolete Ollama pulls
echo  Folder: %CD%
echo ========================================
echo.
echo Stops Ollama, removes 70B wrappers + bases that create.bat
echo must NEVER recreate (euryale / nevoria / dolphin / abliterated / 72b).
echo Safe to run after closing a mid-download create window.
echo.
pause

ollama stop

echo.
echo --- remove wrappers / orphans ---
ollama rm viu-euryale
ollama rm viu-nevoria
ollama rm viu-dolphin
ollama rm viu-abliterated

echo.
echo --- remove heavy bases (ignore if missing) ---
ollama rm huihui_ai/llama3.3-abliterated:70b
ollama rm dolphin-llama3:70b
ollama rm qwen2.5:72b
ollama rm nchapman/l3.3-70b-euryale-v2.3:latest
ollama rm ScrambieBambie/L3.3-MS-Nevoria-70B:i1-Q4_K_M
ollama rm ScrambieBambie/L3.3-MS-Nevoria-70B:latest

echo.
echo --- ollama list ---
ollama list
echo.
echo Next: update Viu to latest, then scripts\create_viu_ollama_models.bat
echo Expect tip line: Set: slim-cydonia-magnum32-commandr-qwen32
echo If tip still lists viu-euryale — files are STALE, do not continue.
echo.
pause
