' Lanza iniciar_servidor.bat sin mostrar ninguna ventana de consola
Dim carpeta
carpeta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("Wscript.Shell").Run """" & carpeta & "\iniciar_servidor.bat""", 0, False
