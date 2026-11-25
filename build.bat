@echo off
REM Compila VFX Explorer como carpeta portable en dist\VFXExplorer
setlocal
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if not exist .venv (
  echo Creando entorno virtual...
  %PY% -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller || goto :error
pyinstaller --noconfirm --clean --windowed --name VFXExplorer --icon assets\icon.ico --collect-all OpenImageIO --collect-all pypdfium2 --collect-all pypdfium2_raw --exclude-module tkinter main.py || goto :error
if not exist dist\VFXExplorer\bin mkdir dist\VFXExplorer\bin
echo Pone aca ffmpeg.exe y ffprobe.exe para thumbnails e info de video> dist\VFXExplorer\bin\LEEME.txt
echo.
echo Listo: dist\VFXExplorer\VFXExplorer.exe
pause
exit /b 0
:error
echo Hubo un error. Revisa que tengas Python 3.10+ instalado (python.org).
pause
exit /b 1
