# Create Desktop + Start Menu launchers for OtaconsKeep (Lite / Expansion).
# Idempotent. Does not print secrets. Safe to re-run after Lite or Expansion.
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
    [string]$OpenBat = ""
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

# Prefer Open-Otacon.bat (wakes WSL / repairs) when present; else open URL directly.
if (-not $OpenBat) {
    $OpenBat = Join-Path $KeepDir "Open-Otacon.bat"
}
$targetPath = $OpenBat
$targetArgs = ""
$workDir = $KeepDir
if (-not (Test-Path -LiteralPath $OpenBat)) {
    # Minimal open bat so Desktop always has something clickable
    $OpenBat = Join-Path $KeepDir "Open-Otacon.bat"
    @"
@echo off
title OtaconsKeep
set "URL=$Url"
if exist "%LOCALAPPDATA%\OtaconsKeep\last-otacon-url.txt" (
  set /p URL=<"%LOCALAPPDATA%\OtaconsKeep\last-otacon-url.txt"
)
start "" "%URL%"
"@ | Set-Content -LiteralPath $OpenBat -Encoding ASCII
    $targetPath = $OpenBat
}

function New-OtaconShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [Parameter(Mandatory = $true)][string]$Target,
        [string]$Arguments = "",
        [string]$WorkingDirectory = "",
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
        $sc.WindowStyle = 1
        $sc.Description = $Description
        # Prefer browser icon when opening via cmd/bat
        $edge = Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"
        $chrome = Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
        if (Test-Path -LiteralPath $edge) {
            $sc.IconLocation = "$edge,0"
        } elseif (Test-Path -LiteralPath $chrome) {
            $sc.IconLocation = "$chrome,0"
        }
        $sc.Save()
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

if ($desktop) {
    $deskLnk = Join-Path $desktop "$safeName.lnk"
    if (New-OtaconShortcut -ShortcutPath $deskLnk -Target $targetPath -WorkingDirectory $workDir `
            -Description "Open $safeName Command Deck ($Url)") {
        $created += $deskLnk
        Write-Host "  Desktop launcher: $deskLnk"
    }
}

$startLnk = Join-Path $startMenu "$safeName.lnk"
if (New-OtaconShortcut -ShortcutPath $startLnk -Target $targetPath -WorkingDirectory $workDir `
        -Description "Open $safeName Command Deck ($Url)") {
    $created += $startLnk
    Write-Host "  Start Menu launcher: $startLnk"
}

# Also write a .url fallback next to Open-Otacon.bat (some corporate policies block .lnk)
$urlShortcut = Join-Path $KeepDir "$safeName.url"
try {
    @"
[InternetShortcut]
URL=$Url
"@ | Set-Content -LiteralPath $urlShortcut -Encoding ASCII
    $created += $urlShortcut
} catch {}

Write-Output ("DESKTOP_LAUNCHER_OK count={0} url={1}" -f $created.Count, $Url)
if ($created.Count -lt 1) { exit 1 }
exit 0
