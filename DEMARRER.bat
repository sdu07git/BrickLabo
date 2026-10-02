@echo off
cd /d "%~dp0"
if exist "BrickLabo.exe" (
    start "" "%~dp0BrickLabo.exe"
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    echo Lancez INSTALLER_DEPENDANCES.bat avant de demarrer les sources.
    pause
)
