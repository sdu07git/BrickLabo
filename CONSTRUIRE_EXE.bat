@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Lancez INSTALLER_DEPENDANCES.bat avant la fabrication.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto erreur
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name BrickLabo --icon "ressources\BrickLabo.ico" --add-data "AIDE.html;." main.py
if errorlevel 1 goto erreur
if exist ressources xcopy /e /i /y ressources dist\BrickLabo\ressources
echo Executable dans dist\BrickLabo. Conserver le dossier complet.
pause
exit /b 0
:erreur
echo Fabrication interrompue. Consultez les messages ci-dessus.
pause
