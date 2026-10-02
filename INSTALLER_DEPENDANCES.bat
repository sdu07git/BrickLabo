@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Pour executer les sources, installez Python 3.12 ou utilisez le paquet portable Windows.
    pause
    exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 goto erreur
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erreur
echo Installation terminee. Lancez DEMARRER.bat.
pause
exit /b 0
:erreur
echo Installation interrompue. Consultez le message ci-dessus.
pause
exit /b 1
