$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path (Get-Location) "diag_nsfw_halves.log"
Write-Host "Folder: $(Get-Location)"
Write-Host "Log:    $log"
if (-not (Test-Path "scripts\diag_viu_nsfw_halves.py")) {
  Write-Host "ERROR: scripts\diag_viu_nsfw_halves.py not found. Update Viu first."
  Read-Host "Press Enter"
  exit 1
}
if (-not $env:VIU_MODEL_REFLECT) { $env:VIU_MODEL_REFLECT = "nchapman/l3.3-70b-euryale-v2.3" }
if (-not $env:VIU_BASE_URL) { $env:VIU_BASE_URL = "http://127.0.0.1:11434/v1" }
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
Write-Host "Model:  $($env:VIU_MODEL_REFLECT)"
Write-Host "Wait - large models are slow..."
if ($py -eq "py") {
  & py -3 "scripts\diag_viu_nsfw_halves.py" *>&1 | Tee-Object -FilePath $log
} else {
  & $py "scripts\diag_viu_nsfw_halves.py" *>&1 | Tee-Object -FilePath $log
}
Write-Host ""
Write-Host "Done. Log: $log"
Read-Host "Press Enter to close"
