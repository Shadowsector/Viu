# Creates a desktop shortcut "Vyu" with the bright icon.
# The file is pure ASCII on purpose: the Russian shortcut name is built from
# Unicode code points, so the script never depends on file encoding.

$desktop = [Environment]::GetFolderPath('Desktop')
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Shortcut name = U+0412 U+044C U+044E (assembled without literal Cyrillic).
$name = -join ([char]0x0412, [char]0x044C, [char]0x044E)
$lnkPath = Join-Path $desktop ($name + '.lnk')

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = (Join-Path $root 'start_viu.vbs')
$lnk.WorkingDirectory = $root
$lnk.IconLocation = (Join-Path $root 'assets\viu_icon.ico')
$lnk.Description = 'Viu - Anabarra companion'
$lnk.Save()

Write-Host ('Done! Desktop shortcut created: ' + $name)
Write-Host 'Launches start_viu.vbs (no black console flash).'
