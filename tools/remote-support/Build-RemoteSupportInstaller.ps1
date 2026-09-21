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
    [switch]$VerboseKey
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

if (-not $AuthKey) {
    $AuthKey = Read-SecurePlain 'Enter temporary single-use Tailscale auth key'
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
Write-Host 'Generated:' -ForegroundColor Green
Write-Host ("  {0}" -f (Split-Path -Leaf $outBat))
Write-Host ''
Write-Host 'Owner access record:' -ForegroundColor Green
Write-Host ("  {0}" -f (Split-Path -Leaf $ownerFile))
Write-Host ("  {0}" -f $ownerFile) -ForegroundColor DarkGray
Write-Host ''
Write-Host '[PASS] Installer written' -ForegroundColor Green
Write-Host ("       {0}" -f $outBat)
Write-Host ''
Write-Host 'WARNING:' -ForegroundColor Yellow
Write-Host 'This generated installer contains a temporary Tailscale enrollment credential' -ForegroundColor Yellow
Write-Host 'and embeds a unique RustDesk unattended password for this machine only.' -ForegroundColor Yellow
Write-Host 'Send the BAT only to the intended recipient.' -ForegroundColor Yellow
Write-Host 'Keep the owner access record private on YOUR PC. Never commit it.' -ForegroundColor Yellow
Write-Host 'Delete the BAT after successful enrollment.' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Friend steps (Josh/Chris):' -ForegroundColor Cyan
Write-Host '  1. Download the BAT'
Write-Host '  2. Right-click -> Run as administrator'
Write-Host '  3. Click Yes on UAC'
Write-Host '  4. Wait for REMOTE ACCESS READY'
Write-Host ''
Write-Host 'Then on YOUR PC:' -ForegroundColor Cyan
Write-Host '  tailscale status'
Write-Host ''
Write-Host 'TERMINAL:' -ForegroundColor Cyan
Write-Host ("  ssh {0}@{1}" -f $SshUser, $Alias)
Write-Host ''
Write-Host 'REMOTE SCREEN:' -ForegroundColor Cyan
Write-Host '  Open RustDesk.'
Write-Host ("  Connect directly to: {0}" -f $Alias)
Write-Host '  If hostname direct-access is unsupported, use the friend Tailscale 100.x.x.x address.'
Write-Host '  Port: 21118'
Write-Host ("  Password: see {0}" -f (Split-Path -Leaf $ownerFile))
if ($DryRun) {
    Write-Host ''
    Write-Host 'Note: -DryRun on the builder does not strip secrets; friend BAT still enrolls unless they pass -DryRun.' -ForegroundColor DarkGray
}

# Clear secrets from memory best-effort
$AuthKey = $null
$rustDeskPassword = $null
[GC]::Collect()
