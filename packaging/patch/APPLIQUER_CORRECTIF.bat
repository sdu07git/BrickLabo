@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLIQUER_CORRECTIF.ps1"
if errorlevel 1 pause
