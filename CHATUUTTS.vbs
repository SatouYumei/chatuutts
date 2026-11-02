Set shell = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
pythonw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
q = Chr(34)
If fso.FileExists(pythonw) Then
    shell.Run q & pythonw & q & " " & q & root & "\app.py" & q, 0, False
Else
    MsgBox "Python was not found. Cannot start CHATUUTTS.", 16, "CHATUUTTS"
End If
