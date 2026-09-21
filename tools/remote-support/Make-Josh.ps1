# OtaconsKeep — one-file owner installer for Josh (download + build friend BAT).
# Designed & Engineered by Antonio G. Garcia // Otaconskeep
# Safe to run from anywhere. Double-clicked via Make-Josh-Installer.bat or:
#   powershell -ExecutionPolicy Bypass -File Make-Josh.ps1

[CmdletBinding()]
param(
    [string]$Recipient = 'Josh',
    [string]$Alias = 'otacon-josh',
    [string]$SshUser = 'Josh'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step([string]$Msg) {
    Write-Host ''
    Write-Host ">>> $Msg" -ForegroundColor Cyan
}

try {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ("  OtaconsKeep — make {0} installer" -f $Recipient) -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green

    $toolDir = Join-Path $env:LOCALAPPDATA 'OtaconsKeep\remote-support'
    $tplDir = Join-Path $toolDir 'templates'
    New-Item -ItemType Directory -Force -Path $tplDir | Out-Null

    $base = 'https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/tools/remote-support'
    $files = @(
        @{ Rel = 'Build-RemoteSupportInstaller.ps1'; Dest = (Join-Path $toolDir 'Build-RemoteSupportInstaller.ps1') },
        @{ Rel = 'RemoteSupport.Common.ps1'; Dest = (Join-Path $toolDir 'RemoteSupport.Common.ps1') },
        @{ Rel = 'templates/RemoteSupportBootstrap.ps1'; Dest = (Join-Path $tplDir 'RemoteSupportBootstrap.ps1') }
    )

    Write-Step 'Downloading toolkit from GitHub (always fresh)...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    foreach ($f in $files) {
        $url = "$base/$($f.Rel)"
        Write-Host ("  {0}" -f $f.Rel)
        Invoke-WebRequest -Uri $url -OutFile $f.Dest -UseBasicParsing
        if (-not (Test-Path -LiteralPath $f.Dest) -or ((Get-Item -LiteralPath $f.Dest).Length -lt 50)) {
            throw "Download failed or empty: $url"
        }
    }
    Write-Host '  Toolkit OK.' -ForegroundColor Green

    Write-Step 'Checking for your SSH public key...'
    $sshDir = Join-Path $env:USERPROFILE '.ssh'
    $pub = $null
    foreach ($n in @('id_ed25519.pub', 'id_ecdsa.pub', 'id_rsa.pub')) {
        $p = Join-Path $sshDir $n
        if (Test-Path -LiteralPath $p) { $pub = $p; break }
    }
    if (-not $pub) {
        Write-Host ''
        Write-Host 'NO SSH PUBLIC KEY FOUND.' -ForegroundColor Red
        Write-Host "Expected a file like: $sshDir\id_ed25519.pub" -ForegroundColor Yellow
        Write-Host ''
        Write-Host 'Create one now in this window? (recommended)' -ForegroundColor Cyan
        Write-Host 'Press Enter to create ed25519 key, or type N then Enter to cancel.'
        $ans = Read-Host 'Create key'
        if ($ans -and $ans.Trim().ToUpperInvariant() -eq 'N') {
            throw 'SSH public key required. Run: ssh-keygen -t ed25519'
        }
        New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
        $keyPath = Join-Path $sshDir 'id_ed25519'
        $gen = Start-Process -FilePath 'ssh-keygen' -ArgumentList @('-t', 'ed25519', '-f', $keyPath, '-N', '', '-C', "otaconskeep-$env:USERNAME") -Wait -PassThru -NoNewWindow
        $pub = "$keyPath.pub"
        if (-not (Test-Path -LiteralPath $pub)) {
            throw 'ssh-keygen did not create a .pub file. Install OpenSSH Client (Windows Optional Features) and retry.'
        }
        Write-Host ("Created {0}" -f $pub) -ForegroundColor Green
    } else {
        Write-Host ("  Found {0}" -f $pub) -ForegroundColor Green
    }

    Write-Step 'Tailscale auth key'
    Write-Host 'Opening Tailscale keys page in your browser...'
    try { Start-Process 'https://login.tailscale.com/admin/settings/keys' } catch {}
    Write-Host '1) Create a key (Reusable OFF / one-time is fine)'
    Write-Host '2) Copy it'
    Write-Host '3) Right-click this window to paste, then press Enter'
    Write-Host ''
    $authKey = Read-Host 'Paste Tailscale auth key here'
    if ($null -eq $authKey) { $authKey = '' }
    $authKey = [string]$authKey
    $authKey = $authKey.Trim()
    if ([string]::IsNullOrWhiteSpace($authKey)) { throw 'No auth key pasted.' }
    if ($authKey -notmatch '^tskey-') {
        Write-Host 'WARNING: key does not start with tskey- — continuing anyway' -ForegroundColor Yellow
    }

    Write-Step 'Building friend installer...'
    Set-Location -LiteralPath $toolDir
    $builder = Join-Path $toolDir 'Build-RemoteSupportInstaller.ps1'
    & $builder -Recipient $Recipient -Alias $Alias -SshUser $SshUser -AuthKey $authKey -PublicKeyPath $pub -CopyToDesktop -OpenOutput

    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Builder exited with code $LASTEXITCODE"
    }

    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop) { $desktop = Join-Path $env:USERPROFILE 'Desktop' }
    $send = Join-Path $desktop ("SEND-TO-{0}.bat" -f $Recipient.ToUpperInvariant())

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host '  SUCCESS' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ("  Send this file to {0}:" -f $Recipient) -ForegroundColor Green
    Write-Host ("  {0}" -f $send) -ForegroundColor Green
    Write-Host ''
    Write-Host ("  {0}: right-click -> Run as administrator -> Yes -> Done" -f $Recipient)
    Write-Host ''
    Write-Host '  After they finish, on YOUR PC:'
    Write-Host ("    ssh {0}@{1}" -f $SshUser, $Alias)
    Write-Host '============================================================' -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host '  FAILED — copy this error to Xof' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.ScriptStackTrace) {
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    }
    Write-Host ''
    exit 1
}
