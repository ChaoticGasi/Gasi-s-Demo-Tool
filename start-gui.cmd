@echo off
setlocal
set "ROOT=%~dp0"

fltmc >nul 2>&1
if not "%errorlevel%"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

cd /d "%ROOT%"

where py >nul 2>&1
if "%errorlevel%"=="0" (
    py -3 "%ROOT%App\desktop_app.py"
    exit /b
)

where python >nul 2>&1
if "%errorlevel%"=="0" (
    python "%ROOT%App\desktop_app.py"
    exit /b
)

echo Python was not found.
echo Install Python 3 from https://www.python.org/downloads/ and make sure "Add python.exe to PATH" is checked.
pause
