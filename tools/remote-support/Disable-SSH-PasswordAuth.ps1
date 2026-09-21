# OtaconsKeep Remote Support — disable SSH password auth AFTER key login works.
# Run ONLY after: ssh <user>@otacon-<friend> succeeds with your private key.
# Designed & Engineered by Antonio G. Garcia // Otaconskeep

[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Merge-Directive([string]$ConfigText, [string]$Directive, [string]$Value) {
    $target = "$Directive $Value"
    $lines = New-Object System.Collections.Generic.List[string]
    $seen = $false
    foreach ($raw in ($ConfigText -split "`r?`n")) {
        if ($raw -match ('^\s*' + [regex]::Escape($Directive) + '\s+')) {
            if (-not $seen) { $lines.Add($target) | Out-Null; $seen = $true }
            continue
        }
        $lines.Add($raw) | Out-Null
    }
    if (-not $seen) { $lines.Add($target) | Out-Null }
    return (($lines -join "`n").TrimEnd() + "`n")
}

Write-Host ''
Write-Host 'OtaconsKeep — Disable SSH Password Authentication' -ForegroundColor Cyan
Write-Host "Don't worry — Otacon's got your back. This only runs after key auth works." -ForegroundColor DarkGray
Write-Host ''

if (-not (Test-IsAdmin)) {
    Write-Host '[FAIL] Administrator privileges required' -ForegroundColor Red
    exit 1
}
Write-Host '[PASS] Administrator privileges' -ForegroundColor Green

$cfg = 'C:\ProgramData\ssh\sshd_config'
if (-not (Test-Path -LiteralPath $cfg)) {
    Write-Host '[FAIL] sshd_config not found' -ForegroundColor Red
    exit 1
}

$backup = "$cfg.otacon-pw-bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
Copy-Item -LiteralPath $cfg -Destination $backup -Force
Write-Host "[PASS] Backup: $backup" -ForegroundColor Green

$raw = Get-Content -LiteralPath $cfg -Raw
$newText = Merge-Directive -ConfigText $raw -Directive 'PubkeyAuthentication' -Value 'yes'
$newText = Merge-Directive -ConfigText $newText -Directive 'PasswordAuthentication' -Value 'no'

if ($DryRun) {
    Write-Host '[PASS] DryRun — would write PasswordAuthentication no' -ForegroundColor Yellow
    exit 0
}

$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($cfg, $newText, $utf8)

$sshd = Join-Path $env:WINDIR 'System32\OpenSSH\sshd.exe'
if (Test-Path -LiteralPath $sshd) {
    $p = Start-Process -FilePath $sshd -ArgumentList @('-t') -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) {
        Copy-Item -LiteralPath $backup -Destination $cfg -Force
        Write-Host '[FAIL] SSH configuration validation failed — restored backup' -ForegroundColor Red
        exit 2
    }
}

try {
    Restart-Service sshd -Force
    Start-Sleep -Seconds 2
} catch {
    Copy-Item -LiteralPath $backup -Destination $cfg -Force
    Write-Host '[FAIL] sshd restart failed — restored backup' -ForegroundColor Red
    exit 3
}

$svc = Get-Service sshd
if ($svc.Status -ne 'Running') {
    Copy-Item -LiteralPath $backup -Destination $cfg -Force
    try { Restart-Service sshd -Force } catch {}
    Write-Host '[FAIL] sshd not Running after change — restored backup' -ForegroundColor Red
    exit 4
}

$listen = Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue
if (-not $listen) {
    Write-Host '[WARN] Port 22 not observed listening yet' -ForegroundColor Yellow
}

$pwOff = Select-String -Path $cfg -Pattern '^\s*PasswordAuthentication\s+no\s*$' -Quiet
$pkOn = Select-String -Path $cfg -Pattern '^\s*PubkeyAuthentication\s+yes\s*$' -Quiet
if (-not $pwOff -or -not $pkOn) {
    Write-Host '[FAIL] Config directives not confirmed' -ForegroundColor Red
    exit 5
}

Write-Host '[PASS] SSH password authentication disabled' -ForegroundColor Green
Write-Host '[PASS] PubkeyAuthentication yes' -ForegroundColor Green
Write-Host '[PASS] sshd Running' -ForegroundColor Green
exit 0
