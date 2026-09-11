@echo off
rem Arranca el servidor de produccion. Lo ejecuta la tarea programada "Servidor Apicultura".
cd /d "%~dp0"
"venv\Scripts\python.exe" -u servidor.py >> servidor.log 2>&1
