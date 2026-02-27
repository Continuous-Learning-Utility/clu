@echo off
:: CLU Daemon - Windows Launcher with auto-restart
:: Usage: run_daemon.bat [--verbose]

setlocal
cd /d "%~dp0"

set VENV=venv\Scripts\python.exe
if not exist "%VENV%" (
    echo Error: Virtual environment not found. Run setup.bat first.
    exit /b 1
)

echo CLU Daemon
echo Press Ctrl+C to stop
echo.

:loop
"%VENV%" -m daemon.daemon %*
echo.
echo Daemon exited. Restarting in 5 seconds... (Ctrl+C to stop)
timeout /t 5 /nobreak >nul
goto loop
