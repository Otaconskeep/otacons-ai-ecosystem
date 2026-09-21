# OtaconsKeep — owner-side launcher (called by Make-Josh/Chris BATs).
# Ensures toolkit under %LOCALAPPDATA%\OtaconsKeep\remote-support, then builds friend BAT.
# Designed & Engineered by Antonio G. Garcia // Otaconskeep

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Recipient,
    [Parameter(Mandatory = $true)][string]$Alias,
    [Parameter(Mandatory = $true)][string]$SshUser,
    [string]$NearbyDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$toolDir = Join-Path $env:LOCALAPPDATA 'OtaconsKeep\remote-support'
$base = 'https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/tools/remote-support'
$files = @(
    'Build-RemoteSupportInstaller.ps1',
    'RemoteSupport.Common.ps1',
    'templates/RemoteSupportBootstrap.ps1'
)

New-Item -ItemType Directory -Force -Path (Join-Path $toolDir 'templates') | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

foreach ($rel in $files) {
    $dest = Join-Path $toolDir ($rel.Replace('/', '\'))
    $copied = $false
    if ($NearbyDir) {
        $cand = Join-Path $NearbyDir ($rel.Replace('/', '\'))
        if (Test-Path -LiteralPath $cand) {
            $parent = Split-Path -Parent $dest
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            Copy-Item -LiteralPath $cand -Destination $dest -Force
            $copied = $true
        }
    }
    if (-not $copied) {
        Write-Host ("Downloading {0} ..." -f $rel)
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Invoke-WebRequest -Uri ("{0}/{1}" -f $base, $rel) -OutFile $dest -UseBasicParsing
    }
}

$builder = Join-Path $toolDir 'Build-RemoteSupportInstaller.ps1'
if (-not (Test-Path -LiteralPath $builder)) {
    throw "Builder missing: $builder"
}

Write-Host ("Toolkit ready at {0}" -f $toolDir)
Write-Host 'Browser will open Tailscale so you can create a one-time key.'
Write-Host 'Paste that key when asked. Everything else is automatic.'
Write-Host ''

Set-Location -LiteralPath $toolDir
& $builder -Recipient $Recipient -Alias $Alias -SshUser $SshUser -CopyToDesktop -OpenOutput -OpenTailscaleKeysPage
exit $LASTEXITCODE
