# Create Desktop + Start Menu launchers for OtaconsKeep (Lite / Expansion).
# Idempotent. Does not print secrets. Safe to re-run after Lite or Expansion.
#
# Daily launch must NOT invoke the setup assistant / repair path (no UAC theater).
# Shortcut opens the Keep URL quietly, with an optional WSL wake ping.
#
# Usage:
#   powershell -File deploy\install-desktop-launcher.ps1 [-Port 5757] [-Url http://127.0.0.1:5757]
#   powershell -File deploy\install-desktop-launcher.ps1 -Label "OtaconsKeep Premium"

[CmdletBinding()]
param(
    [int]$Port = 5757,
    [string]$Url = "",
    [string]$Label = "OtaconsKeep",
    [string]$KeepDir = "",
    [string]$OpenBat = "",
    [string]$DistroName = "Ubuntu-Otacon"
)

$ErrorActionPreference = "Continue"

if (-not $KeepDir) {
    $KeepDir = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
}
New-Item -ItemType Directory -Force -Path $KeepDir | Out-Null

if (-not $Url) {
    $Url = "http://127.0.0.1:$Port"
}
$urlFile = Join-Path $KeepDir "last-otacon-url.txt"
try {
    Set-Content -LiteralPath $urlFile -Value $Url -Encoding ASCII -Force
} catch {}

# Quiet daily launcher (NOT the setup assistant).
$launchCmd = Join-Path $KeepDir "Launch-Otacon.cmd"
$wakePs1 = Join-Path $KeepDir "wake-otacon.ps1"
if (-not (Test-Path -LiteralPath $wakePs1)) {
    $altWake = Join-Path $KeepDir "installer\deploy\wake-otacon.ps1"
    if (Test-Path -LiteralPath $altWake) { $wakePs1 = $altWake }
}

$launchBody = @"
@echo off
setlocal EnableExtensions
title OtaconsKeep
set "URL=$Url"
if exist "%LOCALAPPDATA%\OtaconsKeep\last-otacon-url.txt" (
  set /p URL=<"%LOCALAPPDATA%\OtaconsKeep\last-otacon-url.txt"
)
REM Best-effort quiet wake - never elevates, never opens setup UI.
if exist "%LOCALAPPDATA%\OtaconsKeep\installer\deploy\wake-otacon.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%LOCALAPPDATA%\OtaconsKeep\installer\deploy\wake-otacon.ps1" -DistroName "$DistroName" -Port $Port >nul 2>&1
) else if exist "%LOCALAPPDATA%\OtaconsKeep\wake-otacon.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%LOCALAPPDATA%\OtaconsKeep\wake-otacon.ps1" -DistroName "$DistroName" -Port $Port >nul 2>&1
) else (
  wsl.exe -d $DistroName --exec true >nul 2>&1
)
start "" "%URL%"
exit /b 0
"@
Set-Content -LiteralPath $launchCmd -Value $launchBody -Encoding ASCII

# Keep Open-Otacon.bat as a thin alias to Launch (never the setup assistant).
$openBatPath = if ($OpenBat) { $OpenBat } else { Join-Path $KeepDir "Open-Otacon.bat" }
@"
@echo off
title OtaconsKeep
call "%LOCALAPPDATA%\OtaconsKeep\Launch-Otacon.cmd"
"@ | Set-Content -LiteralPath $openBatPath -Encoding ASCII

$iconPath = Join-Path $KeepDir "otacon-launcher.ico"
$iconSrcCandidates = @(
    (Join-Path $PSScriptRoot "otacon-launcher.ico"),
    (Join-Path $KeepDir "installer\deploy\otacon-launcher.ico")
)
foreach ($src in $iconSrcCandidates) {
    if ($src -and (Test-Path -LiteralPath $src)) {
        try {
            Copy-Item -LiteralPath $src -Destination $iconPath -Force
            break
        } catch {}
    }
}

function New-OtaconShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [Parameter(Mandatory = $true)][string]$Target,
        [string]$Arguments = "",
        [string]$WorkingDirectory = "",
        [string]$Icon = "",
        [string]$Description = "Open OtaconsKeep Command Deck"
    )
    try {
        $dir = Split-Path -Parent $ShortcutPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        $w = New-Object -ComObject WScript.Shell
        $sc = $w.CreateShortcut($ShortcutPath)
        $sc.TargetPath = $Target
        if ($Arguments) { $sc.Arguments = $Arguments }
        if ($WorkingDirectory) { $sc.WorkingDirectory = $WorkingDirectory }
        $sc.WindowStyle = 7  # minimized - hush the brief cmd flash
        $sc.Description = $Description
        if ($Icon -and (Test-Path -LiteralPath $Icon)) {
            $sc.IconLocation = "$Icon,0"
        } else {
            $edge = Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"
            $chrome = Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
            if (Test-Path -LiteralPath $edge) {
                $sc.IconLocation = "$edge,0"
            } elseif (Test-Path -LiteralPath $chrome) {
                $sc.IconLocation = "$chrome,0"
            }
        }
        $sc.Save()
        # Never set the RunAsAdministrator bit on the .lnk
        return $true
    } catch {
        Write-Host ("  WARN: shortcut failed at {0}: {1}" -f $ShortcutPath, $_.Exception.Message)
        return $false
    }
}

$safeName = ($Label -replace '[\\/:*?"<>|]', ' ').Trim()
if (-not $safeName) { $safeName = "OtaconsKeep" }

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\OtaconsKeep"
$created = @()
$targetPath = $launchCmd
$workDir = $KeepDir

if ($desktop) {
    $deskLnk = Join-Path $desktop "$safeName.lnk"
    if (New-OtaconShortcut -ShortcutPath $deskLnk -Target $targetPath -WorkingDirectory $workDir `
            -Icon $iconPath -Description "Open $safeName Command Deck ($Url)") {
        $created += $deskLnk
        Write-Host "  Desktop launcher: $deskLnk"
    }
}

$startLnk = Join-Path $startMenu "$safeName.lnk"
if (New-OtaconShortcut -ShortcutPath $startLnk -Target $targetPath -WorkingDirectory $workDir `
        -Icon $iconPath -Description "Open $safeName Command Deck ($Url)") {
    $created += $startLnk
    Write-Host "  Start Menu launcher: $startLnk"
}

$urlShortcut = Join-Path $KeepDir "$safeName.url"
try {
    $iconLine = ""
    if (Test-Path -LiteralPath $iconPath) {
        $iconLine = "IconFile=$iconPath`r`nIconIndex=0"
    }
    @"
[InternetShortcut]
URL=$Url
$iconLine
"@ | Set-Content -LiteralPath $urlShortcut -Encoding ASCII
    $created += $urlShortcut
} catch {}

Write-Output ("DESKTOP_LAUNCHER_OK count={0} url={1} icon={2}" -f $created.Count, $Url, (Test-Path -LiteralPath $iconPath))
if ($created.Count -lt 1) { exit 1 }
exit 0
