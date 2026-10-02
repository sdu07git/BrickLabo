@echo off
if not exist "%~dp0Donnees\logs" mkdir "%~dp0Donnees\logs"
start "" explorer.exe "%~dp0Donnees\logs"
