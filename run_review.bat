@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" review.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo An error occurred. Check that Python is installed.
pause
