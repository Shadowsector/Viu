$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:VIU_DIAG_TIMEOUT) { $env:VIU_DIAG_TIMEOUT = "1200" }
if (-not $env:VIU_LLM_TIMEOUT) { $env:VIU_LLM_TIMEOUT = "1800" }
if (-not $env:VIU_MODEL_REFLECT) { $env:VIU_MODEL_REFLECT = "viu-magnum" }
if (-not $env:VIU_BASE_URL) { $env:VIU_BASE_URL = "http://127.0.0.1:11434/v1" }
Write-Host "Folder: $(Get-Location)"
Write-Host "Timeout: $($env:VIU_DIAG_TIMEOUT)s"
if (-not (Test-Path "scripts\diag_viu_nsfw_halves.py")) {
  Write-Host "ERROR: script missing. Update Viu first."
  Read-Host "Press Enter"
  exit 1
}
$py = $null
foreach ($c in @("py","python","python3")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break }
}
if (-not $py) {
  Write-Host "ERROR: Python not found in PATH"
  Read-Host "Press Enter"
  exit 1
}
Write-Host "Python: $py"
Write-Host "First run may load 70B for many minutes..."
if ($py -eq "py") { & py -3 -u "scripts\diag_viu_nsfw_halves.py" } else { & $py -u "scripts\diag_viu_nsfw_halves.py" }
$code = $LASTEXITCODE
Write-Host ""
Write-Host "Exit: $code  Log: $((Join-Path (Get-Location) 'diag_nsfw_halves.log'))"
Read-Host "Press Enter to close"
exit $code
