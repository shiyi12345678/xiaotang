' ==========================================================================
'  NetEase Cloud Classroom - silent backend launcher (logon auto-start)
'
'  Runs backend_start.bat with a fully hidden console window, so the backend
'  comes up automatically after you log in without a black window flashing.
'
'  Why a vbs wrapper: a .bat placed directly in the Startup folder always
'  flashes a console window; wscript with window style 0 hides it completely.
'
'  Stop manually:  server\backend_stop.bat
'  Start manually: server\start_server.bat   (shows live logs; best for debug)
'
'  !! KEEP THIS FILE PURE ASCII !!
'  VBScript decodes non-ASCII bytes using the system ANSI code page, so Chinese
'  comments can turn into mojibake and, in the worst case, break parsing.
' ==========================================================================
Option Explicit

Dim fso, sh, baseDir, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

' Directory of this script (server\), so .env and .venv resolve correctly
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = baseDir
batPath = fso.BuildPath(baseDir, "backend_start.bat")

' Arguments: 0 = hidden window, False = do not wait for it to finish
sh.Run "cmd /c """ & batPath & """", 0, False
