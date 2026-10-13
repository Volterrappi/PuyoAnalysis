@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run SETUP_FIRST.bat before launching.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" review.py
if errorlevel 1 (
 echo Application closed with error. Copy the message above when reporting.
 pause
)
