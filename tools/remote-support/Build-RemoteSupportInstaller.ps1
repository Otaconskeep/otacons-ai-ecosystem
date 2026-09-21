# OtaconsKeep Remote Support — owner-side installer builder.
# Creates OtaconsKeep-Remote-Setup-<Recipient>.bat for a friend.
# Designed & Engineered by Antonio G. Garcia // Otaconskeep
#
# Usage:
#   .\tools\remote-support\Build-RemoteSupportInstaller.ps1
#   .\tools\remote-support\Build-RemoteSupportInstaller.ps1 -Recipient Josh -Alias otacon-josh -SshUser Josh
#   .\tools\remote-support\Build-RemoteSupportInstaller.ps1 -DryRun  # builds BAT that runs friend bootstrap in -DryRun

[CmdletBinding()]
param(
    [string]$Recipient,
    [string]$Alias,
    [string]$SshUser,
    [string]$AuthKey,
    [string]$OutputDir,
    [string]$PublicKeyPath,
    [switch]$DryRun,
    [switch]$VerboseKey,
    [switch]$CopyToDesktop,
    [switch]$OpenOutput,
    [switch]$OpenTailscaleKeysPage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
. (Join-Path $here 'RemoteSupport.Common.ps1')

Write-Host (Get-OtaconBanner)

function Read-SecurePlain([string]$Prompt) {
    $sec = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
    }
}

if (-not $Recipient) {
    $Recipient = Read-Host 'Recipient name (example: Josh)'
}
$Recipient = $Recipient.Trim()
if ([string]::IsNullOrWhiteSpace($Recipient)) { throw 'Recipient name is required' }

$defaultAlias = ConvertTo-OtaconSafeAlias -Name $Recipient
if (-not $Alias) {
    $a = Read-Host "Remote machine alias [$defaultAlias]"
    if ([string]::IsNullOrWhiteSpace($a)) { $Alias = $defaultAlias } else { $Alias = ConvertTo-OtaconSafeAlias -Name $a }
} else {
    $Alias = ConvertTo-OtaconSafeAlias -Name $Alias
}

if (-not $SshUser) {
    $u = Read-Host "Windows SSH username [$Recipient]"
    if ([string]::IsNullOrWhiteSpace($u)) { $SshUser = $Recipient } else { $SshUser = $u.Trim() }
} else {
    $SshUser = $SshUser.Trim()
}

# Discover public key — never private
$pubPath = $PublicKeyPath
if (-not $pubPath) {
    $pubPath = Find-OtaconSshPublicKeyPath
}
if (-not $pubPath) {
    throw 'No SSH public key found. Expected %USERPROFILE%\.ssh\id_ed25519.pub (or id_ecdsa.pub / id_rsa.pub).'
}
$pubLine = Read-OtaconSshPublicKey -Path $pubPath
Write-Host '[PASS] SSH public key found' -ForegroundColor Green
Write-Host ("       Path: {0}" -f $pubPath) -ForegroundColor DarkGray
if ($VerboseKey) {
    Write-Host ("       Key:  {0}" -f $pubLine) -ForegroundColor DarkGray
} else {
    $parts = $pubLine.Split(' ', 3)
    $preview = if ($parts.Length -ge 2) { "{0} {1}…" -f $parts[0], $parts[1].Substring(0, [Math]::Min(12, $parts[1].Length)) } else { '(ok)' }
    Write-Host ("       Preview: {0}" -f $preview) -ForegroundColor DarkGray
}

if ($OpenTailscaleKeysPage) {
    Write-Host 'Opening Tailscale auth-keys page in your browser…' -ForegroundColor Cyan
    try { Start-Process 'https://login.tailscale.com/admin/settings/keys' } catch {}
    Write-Host 'Create a one-time / reusable=off key, copy it, then paste below.' -ForegroundColor DarkGray
    Write-Host ''
}

if (-not $AuthKey) {
    $AuthKey = Read-SecurePlain 'Paste Tailscale auth key (only thing you type)'
}
$AuthKey = $AuthKey.Trim()
if ([string]::IsNullOrWhiteSpace($AuthKey)) { throw 'Tailscale auth key is required' }
if ($AuthKey -notmatch '^tskey-') {
    Write-Host '[WARN] Auth key does not start with tskey- — continuing anyway' -ForegroundColor Yellow
}

$rustDeskPassword = New-OtaconRustDeskPassword
Write-Host '[PASS] Unique RustDesk unattended password generated' -ForegroundColor Green
Write-Host '       (stored only in owner access record — never shown to friend)' -ForegroundColor DarkGray

$templatePath = Join-Path $here 'templates\RemoteSupportBootstrap.ps1'
if (-not (Test-Path -LiteralPath $templatePath)) { throw "Missing template: $templatePath" }
$template = Get-Content -LiteralPath $templatePath -Raw

# Escape nothing exotic — replace placeholders carefully; pubkey/auth may contain $
$embedded = $template
$embedded = $embedded.Replace('{{RECIPIENT}}', $Recipient)
$embedded = $embedded.Replace('{{ALIAS}}', $Alias)
$embedded = $embedded.Replace('{{SSH_USER}}', $SshUser)
$embedded = $embedded.Replace('{{SSH_PUBKEY}}', $pubLine)
$embedded = $embedded.Replace('{{TS_AUTH_KEY}}', $AuthKey)
$embedded = $embedded.Replace('{{RUSTDESK_PASSWORD}}', $rustDeskPassword)

if (Test-OtaconPrivateKeyLeak -Text $embedded) {
    throw 'Refusing to build installer: private key material detected in payload'
}

$bat = New-OtaconRemoteBatWrapper -EmbeddedPs1 $embedded -Recipient $Recipient
if (Test-OtaconPrivateKeyLeak -Text $bat) {
    throw 'Refusing to write BAT: private key material detected'
}
# Public key must be present; private must not
if ($bat -notlike "*$($pubLine.Split(' ')[0])*") {
    # base64 embed — check decoded payload instead
    if ($embedded -notlike "*$pubLine*") { throw 'Generated payload missing public key' }
}
if ($embedded -notlike "*$Alias*") { throw 'Generated payload missing alias' }

$safeName = ($Recipient -replace '[^\w\-]', '')
if ([string]::IsNullOrWhiteSpace($safeName)) { $safeName = 'Friend' }
if (-not $OutputDir) {
    $OutputDir = Join-Path $here 'out'
}
if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}
$outBat = Join-Path $OutputDir ("OtaconsKeep-Remote-Setup-{0}.bat" -f $safeName)

# Ensure CRLF
$crlf = $bat -replace "(?<!\r)\n", "`r`n"
[IO.File]::WriteAllText($outBat, $crlf, (New-Object System.Text.UTF8Encoding $false))

$desktopBat = $null
if ($CopyToDesktop) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop)) { $desktop = Join-Path $env:USERPROFILE 'Desktop' }
    if (-not (Test-Path -LiteralPath $desktop)) {
        New-Item -ItemType Directory -Force -Path $desktop | Out-Null
    }
    $desktopBat = Join-Path $desktop ("SEND-TO-{0}.bat" -f $safeName.ToUpperInvariant())
    Copy-Item -LiteralPath $outBat -Destination $desktopBat -Force
}

$ownerDir = Join-Path $here 'generated\owner'
if (-not (Test-Path -LiteralPath $ownerDir)) {
    New-Item -ItemType Directory -Force -Path $ownerDir | Out-Null
}
$ownerFile = Join-Path $ownerDir ("{0}-RemoteAccess.txt" -f $safeName)
$ownerBody = @"
OTACONSKEEP OWNER ACCESS RECORD — PROTECT THIS FILE
Contains remote-control credentials. Do not commit. Do not share with the friend.

Recipient:
$Recipient

Alias:
$Alias

Windows user:
$SshUser

Preferred SSH:
ssh ${SshUser}@${Alias}

Fallback SSH:
ssh ${SshUser}@<friend-tailscale-100.x.x.x>

RustDesk address:
$Alias

RustDesk fallback address:
<friend-tailscale-100.x.x.x>

RustDesk direct port:
21118

RustDesk unattended password:
$rustDeskPassword

After friend installer succeeds:

TERMINAL:
  ssh ${SshUser}@${Alias}

REMOTE SCREEN:
  Open RustDesk.
  Connect directly to: $Alias
  If hostname direct-access resolution is unsupported, use the Tailscale 100.x.x.x address.
  Port: 21118
  Password: (value above)

Notes:
- Primary graphical path is RustDesk over Tailscale (not public relay).
- Native Windows RDP host is optional and NOT required; do not expose TCP 3389.
- Friend must not see this password.
"@
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($ownerFile, ($ownerBody -replace "(?<!\r)\n", "`r`n"), $utf8)

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ("  SEND THIS FILE TO {0}:" -f $Recipient.ToUpperInvariant()) -ForegroundColor Green
if ($desktopBat) {
    Write-Host ("  {0}" -f $desktopBat) -ForegroundColor Green
} else {
    Write-Host ("  {0}" -f $outBat) -ForegroundColor Green
}
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Also saved:' -ForegroundColor DarkGray
Write-Host ("  {0}" -f $outBat) -ForegroundColor DarkGray
Write-Host ("  Owner record (KEEP PRIVATE): {0}" -f $ownerFile) -ForegroundColor DarkGray
Write-Host ''
Write-Host ("{0} only needs to: Run as administrator → Yes → Done." -f $Recipient) -ForegroundColor Cyan
Write-Host ''
Write-Host 'After they finish, on YOUR PC:' -ForegroundColor Cyan
Write-Host ("  ssh {0}@{1}" -f $SshUser, $Alias)
Write-Host ("  RustDesk → {0}  port 21118  (password in owner record)" -f $Alias)

if ($OpenOutput) {
    $reveal = if ($desktopBat) { $desktopBat } else { $outBat }
    try { Start-Process explorer.exe -ArgumentList ('/select,"{0}"' -f $reveal) } catch {}
}

if ($DryRun) {
    Write-Host ''
    Write-Host 'Note: -DryRun on the builder does not strip secrets; friend BAT still enrolls unless they pass -DryRun.' -ForegroundColor DarkGray
}

# Clear secrets from memory best-effort
$AuthKey = $null
$rustDeskPassword = $null
[GC]::Collect()
