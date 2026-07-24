' Запуск Viu.cmd без чёрного окна (см. VIU_SHOW_CONSOLE=1 для отладки).
Option Explicit
Dim fso, sh, installDir, args, i, a, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
installDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")

args = ""
For i = 0 To WScript.Arguments.Count - 1
  a = WScript.Arguments(i)
  args = args & " " & Chr(34) & Replace(a, Chr(34), Chr(34) & Chr(34)) & Chr(34)
Next

cmd = "cmd /c " & Chr(34) & installDir & "\Viu.cmd" & Chr(34) & " _hidden _run" & args
sh.Run cmd, 0, False
