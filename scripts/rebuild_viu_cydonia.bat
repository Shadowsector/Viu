@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

echo ========================================
echo  Rebuild viu-cydonia (UTF-8 Modelfile)
echo  Folder: %CD%
echo ========================================
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo ERROR: ollama.exe not in PATH.
  exit /b 1
)

if not exist "ollama\Modelfile.viu-cydonia.example" (
  echo ERROR: нет ollama\Modelfile.viu-cydonia.example — обнови Viu.
  exit /b 1
)

echo [1/4] Копирую .example -^> рабочий Modelfile ^(UTF-8^)...
powershell -NoProfile -Command ^
  "Get-Content -LiteralPath 'ollama\Modelfile.viu-cydonia.example' -Encoding UTF8 | Set-Content -LiteralPath 'ollama\Modelfile.viu-cydonia' -Encoding utf8"
if errorlevel 1 (
  echo PowerShell не смог — пробую copy...
  copy /y "ollama\Modelfile.viu-cydonia.example" "ollama\Modelfile.viu-cydonia" >nul
)

echo [2/4] Останавливаю модель, если запущена...
ollama stop viu-cydonia 2>nul

echo [3/4] Удаляю старый тег ^(not found — нормально^)...
ollama rm viu-cydonia 2>nul

echo [4/4] ollama create viu-cydonia ...
ollama create viu-cydonia -f "ollama\Modelfile.viu-cydonia"
if errorlevel 1 (
  echo.
  echo FAIL. Открой ollama\Modelfile.viu-cydonia и проверь:
  echo   - первая строка FROM ...
  echo   - блок SYSTEM начинается с SYSTEM """ и кончается строкой """
  echo   - файл UTF-8, не UTF-16
  echo   - база FROM уже есть: ollama list ^| findstr /i cydonia
  exit /b 1
)

echo.
echo OK. Проверка SYSTEM:
ollama show viu-cydonia --modelfile | findstr /i /c:"Если русское" /c:"Ты — Вью" /c:"SYSTEM"
echo.
echo В .env: VIU_MODEL_REFLECT=viu-cydonia
echo Перезапусти Viu, лучше новый чат.
exit /b 0
