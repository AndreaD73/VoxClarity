' Launches VoxClarity without a console window (drop a file on this script to preselect it).
Set sh = CreateObject("WScript.Shell")
here = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
py = here & "\.venv\Scripts\pythonw.exe"
If Not CreateObject("Scripting.FileSystemObject").FileExists(py) Then
  MsgBox "VoxClarity is not installed yet. Run install.ps1 first (right-click > Run with PowerShell).", 48, "VoxClarity"
  WScript.Quit 1
End If
cmd = """" & py & """ """ & here & "\server.py"""
If WScript.Arguments.Count > 0 Then cmd = cmd & " """ & WScript.Arguments(0) & """"
sh.CurrentDirectory = here
sh.Run cmd, 0, False
