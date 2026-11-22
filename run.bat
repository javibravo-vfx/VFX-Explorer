@echo off
REM Corre VFX Explorer desde el codigo, sin compilar (requiere haber corrido build.bat una vez)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
start "" pythonw main.py %*
