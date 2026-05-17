@echo off
rmdir /s /q .venv 2>nul
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
echo.
echo Entorno listo y dependencias instaladas.
pause