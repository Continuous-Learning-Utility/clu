@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: ============================================================
::  CLU - Auto Setup
::  Detects Python, installs it if missing, creates the venv,
::  installs dependencies. Idempotent (can be re-run safely).
:: ============================================================

set "AGENT_DIR=%~dp0"
set "AGENT_DIR=%AGENT_DIR:~0,-1%"
set "VENV_DIR=%AGENT_DIR%\venv"
set "PYTHON_CMD="
set "SETUP_MARKER=%VENV_DIR%\.setup_done"

echo.
echo ========================================
echo   CLU - Setup
echo ========================================
echo.

:: -------------------------------------------------------
:: Step 1: Find Python
:: -------------------------------------------------------
echo [1/4] Looking for Python...

:: Try python in PATH
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    set "PYTHON_CMD=python"
    goto :python_found
)

:: Try python3 in PATH
python3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
    set "PYTHON_CMD=python3"
    goto :python_found
)

:: Try common install locations
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist %%p (
        for /f "tokens=2" %%v in ('%%p --version 2^>^&1') do set "PY_VER=%%v"
        set "PYTHON_CMD=%%p"
        goto :python_found
    )
)

:: Python not found - auto install
echo [WARN] Python not found. Installing automatically...
echo.
goto :install_python

:python_found
echo [  OK] Python %PY_VER% found: %PYTHON_CMD%
goto :check_venv

:: -------------------------------------------------------
:: Step 2: Auto-install Python
:: -------------------------------------------------------
:install_python
echo [2/4] Installing Python...

:: Run PowerShell installer script
powershell -ExecutionPolicy Bypass -File "%AGENT_DIR%\scripts\install_python.ps1"
set "PS_EXIT=%ERRORLEVEL%"

if %PS_EXIT% EQU 0 (
    echo [  OK] Python installed successfully
) else if %PS_EXIT% EQU 2 (
    echo.
    echo ================================================
    echo   Python installed, but PATH is not up to date.
    echo   CLOSE this terminal and re-run setup.bat
    echo ================================================
    echo.
    pause
    exit /b 2
) else (
    echo.
    echo ================================================
    echo   FAILED: Unable to install Python.
    echo   Install Python 3.12 manually:
    echo   https://python.org/downloads/
    echo   Check "Add Python to PATH" during installation.
    echo ================================================
    echo.
    pause
    exit /b 1
)

:: Refresh PATH and re-detect Python
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

:: Re-check after install
for %%p in (
    "python"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do (
    %%~p --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        for /f "tokens=2" %%v in ('%%~p --version 2^>^&1') do set "PY_VER=%%v"
        set "PYTHON_CMD=%%~p"
        goto :check_venv
    )
)

echo [ERROR] Python not found after installation. Re-run setup.bat in a new terminal.
pause
exit /b 1

:: -------------------------------------------------------
:: Step 3: Create/check virtual environment
:: -------------------------------------------------------
:check_venv
echo [2/4] Checking virtual environment...

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [  OK] venv already exists
    goto :install_deps
)

echo       Creating venv...
%PYTHON_CMD% -m venv "%VENV_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create venv
    pause
    exit /b 1
)
echo [  OK] venv created

:: -------------------------------------------------------
:: Step 4: Install dependencies
:: -------------------------------------------------------
:install_deps
echo [3/4] Installing dependencies...

:: Upgrade pip first
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet 2>nul

:: Install requirements
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%AGENT_DIR%\requirements.txt" --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] pip install returned an error, retrying without --quiet...
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%AGENT_DIR%\requirements.txt"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo [  OK] Dependencies installed

:: -------------------------------------------------------
:: Step 5: Verify setup
:: -------------------------------------------------------
echo [4/4] Final verification...

"%VENV_DIR%\Scripts\python.exe" -c "import openai; import yaml; import jsonschema; print('All imports OK')"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Import verification failed
    pause
    exit /b 1
)

:: Write setup marker
echo %date% %time% > "%SETUP_MARKER%"

echo.
echo ========================================
echo   Setup completed successfully!
echo ========================================
echo   Python: %PY_VER%
echo   Venv:   %VENV_DIR%
echo.
echo   Use run.bat to launch the agent
echo   or directly:
echo     venv\Scripts\python main.py --help
echo ========================================
echo.

exit /b 0
