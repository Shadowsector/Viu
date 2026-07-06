' Запуск Вью без мелькания чёрного окна (Windows Script Host).
Option Explicit

Dim fso, shell, folder, pyw, cmd, env, logPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

' Переменные из start_viu.bat (дублируем для прямого запуска VBS)
shell.Environment("PROCESS")("PYTHONUTF8") = "1"
shell.Environment("PROCESS")("PYTHONPATH") = folder
shell.Environment("PROCESS")("VIU_PROVIDER") = "openai"
shell.Environment("PROCESS")("VIU_BASE_URL") = "http://localhost:11434/v1"
shell.Environment("PROCESS")("VIU_API_KEY") = "ollama"
shell.Environment("PROCESS")("VIU_MODEL") = "qwen2.5-coder:14b"
shell.Environment("PROCESS")("VIU_UNITY_PROJECT") = "U:\Anabarra\Unity\Anabarra"
shell.Environment("PROCESS")("VIU_ANIM_STAGING") = "U:\Anabarra\Animations"
shell.Environment("PROCESS")("VIU_AUTO_UPDATE") = "1"

logPath = folder & "\viu_startup.log"

' 1) py -3w (лаунчер Python на Windows)
cmd = "py -3w """ & folder & "\run_gui.pyw"""
If RunHidden(cmd) = 0 Then WScript.Quit 0

' 2) pythonw рядом с python
pyw = FindPythonw()
If pyw <> "" Then
  cmd = """" & pyw & """ """ & folder & "\run_gui.pyw"""
  If RunHidden(cmd) = 0 Then WScript.Quit 0
End If

' 3) python + run_gui.pyw (последний шанс, может мелькнуть — но покажет ошибку)
cmd = "cmd /c cd /d """ & folder & """ && python """ & folder & "\run_gui.pyw"" >> """ & logPath & """ 2>&1"
shell.Run cmd, 1, True
WScript.Quit 1

Function RunHidden(command)
  On Error Resume Next
  shell.CurrentDirectory = folder
  RunHidden = shell.Run(command, 0, False)
  If Err.Number <> 0 Then RunHidden = 1
  On Error GoTo 0
End Function

Function FindPythonw()
  Dim paths, p, base
  paths = Array( _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python312\pythonw.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python311\pythonw.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python310\pythonw.exe"), _
    "C:\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe" _
  )
  For Each p In paths
    If fso.FileExists(p) Then
      FindPythonw = p
      Exit Function
    End If
  Next
  FindPythonw = ""
End Function
