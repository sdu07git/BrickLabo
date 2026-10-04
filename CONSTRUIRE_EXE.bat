@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Lancez INSTALLER_DEPENDANCES.bat avant la fabrication. / Run INSTALLER_DEPENDANCES.bat before building.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto erreur
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name BrickLabo --icon "ressources\BrickLabo.ico" --add-data "AIDE.html;." --add-data "AIDE.en.html;." --add-data "SOURCES_ET_LICENCES.html;." --add-data "SOURCES_ET_LICENCES.en.html;." --add-data "ressources;ressources" --add-data "licences;licences" main.py
if errorlevel 1 goto erreur
echo Executable dans dist\BrickLabo. Conserver le dossier complet. / Executable in dist\BrickLabo. Keep the entire folder.
pause
exit /b 0
:erreur
echo Fabrication interrompue. Consultez les messages ci-dessus. / Build stopped. Check the messages above.
pause
