# Создаёт на рабочем столе ярлык «Вью» с яркой иконкой.
$desktop = [Environment]::GetFolderPath('Desktop')
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop 'Вью.lnk'))
$lnk.TargetPath = (Join-Path $root 'start_viu.bat')
$lnk.WorkingDirectory = $root
$lnk.IconLocation = (Join-Path $root 'assets\viu_icon.ico')
$lnk.Description = 'Вью — помощник и соавтор Анабарры'
$lnk.Save()

Write-Host 'Готово! Ярлык "Вью" создан на рабочем столе.'
