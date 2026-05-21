<#
.SYNOPSIS
    MAREF Unified Compliance Sidecar — Windows Service Installation

.DESCRIPTION
    Installs the UnifiedSidecar as a Windows Service using NSSM
    (Non-Sucking Service Manager).

.PARAMETER Action
    install | uninstall | start | stop | status

.EXAMPLE
    .\install_windows_service.ps1 -Action install
    .\install_windows_service.ps1 -Action start

.NOTES
    Requires: NSSM (https://nssm.cc) installed in PATH or C:\tools\nssm.exe
    Logs: C:\ProgramData\MAREF\logs\sidecar\
#>

param(
    [ValidateSet("install", "uninstall", "start", "stop", "status")]
    [string]$Action = "status"
)

$ServiceName = "MAREFComplianceSidecar"
$DisplayName = "MAREF Unified Compliance Sidecar"
$Description = "Combined MAREF governance + MAS-TS-001 compliance sidecar"

$ProjectRoot = "C:\MAREF"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
$Module = "sidecar.server"
$LogDir = "C:\ProgramData\MAREF\logs\sidecar"
$Nssm = "nssm.exe"

function Test-Requirements {
    if (-not (Get-Command $Nssm -ErrorAction SilentlyContinue)) {
        Write-Warning "NSSM not found in PATH. Installing..."
        $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
        $temp = "$env:TEMP\nssm.zip"
        Invoke-WebRequest -Uri $nssmUrl -OutFile $temp
        Expand-Archive -Path $temp -DestinationPath "C:\tools\nssm" -Force
        $script:Nssm = "C:\tools\nssm\nssm-2.24\win64\nssm.exe"
    }
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
}

function Install-Service {
    Test-Requirements
    & $Nssm install $ServiceName $Python "-m $Module --host 127.0.0.1 --port 8099"
    & $Nssm set $ServiceName DisplayName $DisplayName
    & $Nssm set $ServiceName Description $Description
    & $Nssm set $ServiceName AppDirectory $ProjectRoot
    & $Nssm set $ServiceName AppStdout "$LogDir\stdout.log"
    & $Nssm set $ServiceName AppStderr "$LogDir\stderr.log"
    & $Nssm set $ServiceName AppRotateFiles 1
    & $Nssm set $ServiceName AppRotateSeconds 86400
    & $Nssm set $ServiceName AppRotateBytes 10485760
    & $Nssm set $ServiceName Start SERVICE_AUTO_START
    & $Nssm set $ServiceName ObjectName LocalSystem
    & $Nssm set $ServiceName AppThrottle 5000
    Write-Host "[OK] Service '$ServiceName' installed" -ForegroundColor Green
}

function Uninstall-Service {
    & $Nssm stop $ServiceName 2>$null
    & $Nssm remove $ServiceName confirm
    Write-Host "[OK] Service '$ServiceName' removed" -ForegroundColor Yellow
}

function Start-Service {
    & $Nssm start $ServiceName
    Write-Host "[OK] Service '$ServiceName' started" -ForegroundColor Green
}

function Stop-Service {
    & $Nssm stop $ServiceName
    Write-Host "[OK] Service '$ServiceName' stopped" -ForegroundColor Yellow
}

function Status-Service {
    & $Nssm status $ServiceName
}

switch ($Action) {
    "install"   { Install-Service }
    "uninstall" { Uninstall-Service }
    "start"     { Start-Service }
    "stop"      { Stop-Service }
    "status"    { Status-Service }
}
