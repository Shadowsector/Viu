@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
chcp 65001 >nul
echo ========================================
echo  Remove heavy / obsolete Ollama models
echo ========================================
echo.
echo Will try to remove (ignore errors if already gone):
echo   70B: abliterated, dolphin, viu-dolphin, viu-abliterated
echo   72B: qwen2.5:72b
echo   orphans: viu-euryale, viu-nevoria
echo   old magnum base (optional): fluffy/magnum-v3-34b
echo.
echo Close Ollama chats using these models first.
echo.
pause

ollama stop

echo.
echo --- removing ---
ollama rm huihui_ai/llama3.3-abliterated:70b
ollama rm dolphin-llama3:70b
ollama rm viu-dolphin
ollama rm viu-abliterated
ollama rm qwen2.5:72b
ollama rm viu-euryale
ollama rm viu-nevoria
ollama rm nchapman/l3.3-70b-euryale-v2.3:latest
ollama rm ScrambieBambie/L3.3-MS-Nevoria-70B:i1-Q4_K_M

echo.
set /p OLDMAG=Also remove fluffy/magnum-v3-34b (replaced by bartowski 32B)? [y/N]: 
if /i "%OLDMAG%"=="y" (
  ollama rm fluffy/magnum-v3-34b:latest
  ollama rm viu-magnum
  echo Removed old magnum. Re-run create_viu_ollama_models.bat for new viu-magnum.
)

echo.
echo --- ollama list ---
ollama list
echo.
echo Next: update Viu, then create_viu_ollama_models.bat
echo Expect banner: Set: slim-cydonia-magnum32-commandr-qwen32
echo Emergency after bad create: abort_heavy_ollama.bat
echo.
pause
