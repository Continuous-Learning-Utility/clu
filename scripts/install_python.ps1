#Requires -Version 5.1
<#
.SYNOPSIS
    Installs Python 3.12 automatically via winget or direct download.
.DESCRIPTION
    1. Checks if Python 3.10+ is already installed
    2. Attempts installation via winget (Windows Package Manager)
    3. On failure, downloads the installer from python.org
    4. Adds Python to the user PATH
#>

param(
    [string]$MinVersion = "3.10",
    [string]$TargetVersion = "3.12"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "[SETUP] $msg" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "[  OK ] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "[ WARN] $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
}

function Test-PythonInstalled {
    # Check common Python locations
    $candidates = @(
        "python",
        "python3",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )

    foreach ($candidate in $candidates) {
        try {
            $output = & $candidate --version 2>&1
            if ($output -match "Python (\d+\.\d+\.\d+)") {
                $foundVersion = $Matches[1]
                $major, $minor, $_ = $foundVersion.Split(".")
                $minMajor, $minMinor = $MinVersion.Split(".")

                if ([int]$major -gt [int]$minMajor -or
                    ([int]$major -eq [int]$minMajor -and [int]$minor -ge [int]$minMinor)) {

                    # Resolve full path
                    $resolvedPath = $candidate
                    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
                        $resolvedPath = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
                    }

                    return @{
                        Found   = $true
                        Version = $foundVersion
                        Path    = $resolvedPath
                    }
                }
            }
        }
        catch {
            # Candidate not found, continue
        }
    }

    return @{ Found = $false }
}

function Install-PythonWinget {
    Write-Step "Installing Python $TargetVersion via winget..."

    try {
        $wingetVersion = & winget --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "winget not available"
        }
        Write-Step "winget detected: $wingetVersion"
    }
    catch {
        Write-Warn "winget not available, falling back to direct download"
        return $false
    }

    try {
        # Accept source agreements automatically
        & winget install "Python.Python.$TargetVersion" `
            --accept-source-agreements `
            --accept-package-agreements `
            --silent `
            --scope user 2>&1 | ForEach-Object { Write-Host "  $_" }

        if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
            # -1978335189 = already installed
            Write-Ok "Python installed via winget"
            Refresh-Path
            return $true
        }
        else {
            Write-Warn "winget returned code $LASTEXITCODE"
            return $false
        }
    }
    catch {
        Write-Warn "winget failed: $_"
        return $false
    }
}

function Install-PythonDirect {
    Write-Step "Downloading Python from python.org..."

    $installerUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-installer.exe"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

        if (-not (Test-Path $installerPath)) {
            throw "Download failed"
        }

        $fileSize = (Get-Item $installerPath).Length
        Write-Step "Installer downloaded ($([math]::Round($fileSize / 1MB, 1)) MB)"

        Write-Step "Running silent installation..."
        $process = Start-Process -FilePath $installerPath `
            -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_test=0" `
            -Wait -PassThru

        if ($process.ExitCode -eq 0) {
            Write-Ok "Python installed from python.org"
            Refresh-Path
            return $true
        }
        else {
            Write-Err "Installer returned code $($process.ExitCode)"
            return $false
        }
    }
    catch {
        Write-Err "Download/installation failed: $_"
        return $false
    }
    finally {
        if (Test-Path $installerPath) {
            Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Refresh-Path {
    # Reload PATH from registry to pick up newly installed Python
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$userPath;$machinePath"
}

# ============================================================
# MAIN
# ============================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Python Auto-Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if Python is already installed
Write-Step "Checking for Python..."
$result = Test-PythonInstalled

if ($result.Found) {
    Write-Ok "Python $($result.Version) detected: $($result.Path)"
    Write-Host $result.Path
    exit 0
}

Write-Warn "Python $MinVersion+ not found"

# Step 2: Try winget
$installed = Install-PythonWinget

if (-not $installed) {
    # Step 3: Fallback to direct download
    $installed = Install-PythonDirect
}

if (-not $installed) {
    Write-Err "Unable to install Python automatically."
    Write-Err "Install Python 3.12 manually from https://python.org/downloads/"
    exit 1
}

# Step 4: Verify installation
Start-Sleep -Seconds 2
Refresh-Path
$result = Test-PythonInstalled

if ($result.Found) {
    Write-Ok "Verification: Python $($result.Version) ready"
    Write-Host $result.Path
    exit 0
}
else {
    Write-Warn "Python installed but not yet in this session's PATH."
    Write-Warn "Close and reopen your terminal, then re-run setup.bat"
    exit 2
}
