@echo off
setlocal

set "ROOT=%~dp0"
set "APP=%ROOT%App\desktop_app.py"

where py >nul 2>nul
if not errorlevel 1 (
    py "%APP%"
    exit /b %errorlevel%
)

where python >nul 2>nul
if not errorlevel 1 (
    python "%APP%"
    exit /b %errorlevel%
)

where python3 >nul 2>nul
if not errorlevel 1 (
    python3 "%APP%"
    exit /b %errorlevel%
)

echo Python was not found. Install Python and make sure it is available from the command line.
pause
exit /b 1
