@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: ============================================================
::  CLU - Launcher
::  Auto-setup if needed, then launches the agent.
::
::  Usage:
::    run.bat --web                                           (dashboard, no --project needed)
::    run.bat --web --project "D:\PROJECTS\MyProject"         (dashboard with pre-loaded project)
::    run.bat --project "D:\PROJECTS\MyProject" --task "..."  (CLI mode)
::    run.bat --project "D:\PROJECTS\MyProject" --interactive (REPL mode)
::    run.bat --help
:: ============================================================

set "AGENT_DIR=%~dp0"
set "AGENT_DIR=%AGENT_DIR:~0,-1%"
set "VENV_DIR=%AGENT_DIR%\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "SETUP_MARKER=%VENV_DIR%\.setup_done"

:: -------------------------------------------------------
:: Check if setup is needed
:: -------------------------------------------------------
if not exist "%VENV_PYTHON%" goto :needs_setup
if not exist "%SETUP_MARKER%" goto :needs_setup
goto :run_agent

:needs_setup
echo Agent not configured. Running automatic setup...
echo.
call "%AGENT_DIR%\setup.bat"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Setup failed. Fix the errors above then re-run run.bat
    pause
    exit /b 1
)

:: Re-check after setup
if not exist "%VENV_PYTHON%" (
    echo [ERROR] venv still does not exist after setup.
    pause
    exit /b 1
)

echo.

:: -------------------------------------------------------
:: Run the agent
:: -------------------------------------------------------
:run_agent

:: If no arguments, launch web dashboard by default
if "%~1"=="" (
    echo Launching web dashboard...
    echo.
    "%VENV_PYTHON%" "%AGENT_DIR%\main.py" --web
    exit /b %ERRORLEVEL%
)

"%VENV_PYTHON%" "%AGENT_DIR%\main.py" %*
exit /b %ERRORLEVEL%
