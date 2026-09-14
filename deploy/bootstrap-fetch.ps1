# OtaconsKeep bootstrap file fetch — stdout/stderr + exit codes for the BAT wrapper.
# No git. Safe to re-run. Does not store credentials.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DestRoot,
    [Parameter(Mandatory = $true)][string]$RawBase,
    [Parameter(Mandatory = $true)][string]$LogFile,
    [string]$Manifest = "full",
    [switch]$DebugMode
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffK"
    $line = "[$ts] [$Level] [FETCH] $Message"
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
    if ($DebugMode) { Write-Host $line }
}

function Show-Status {
    param([string]$StepLabel, [string]$Source, [string]$Status, [string]$File = "")
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkYellow
    Write-Host "  $StepLabel" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkYellow
    if ($File) {
        Write-Host "  file"
        Write-Host "  $File"
        Write-Host ""
    }
    Write-Host "  source"
    Write-Host "  $Source"
    Write-Host ""
    Write-Host "  status"
    Write-Host "  $Status" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor DarkYellow
    Write-Host ""
}

# Manifest: which relative paths to pull from RawBase into DestRoot
$full = @(
    "install_otacon.bat",
    "OtaconsKeep-Setup.bat",
    "deploy/windows-setup-assistant.ps1",
    "deploy/bootstrap-fetch.ps1",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/wake-otacon.ps1"
)
$deployOnly = @(
    "deploy/windows-setup-assistant.ps1",
    "deploy/bootstrap-fetch.ps1",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/wake-otacon.ps1"
)

$files = if ($Manifest -eq "deploy") { $deployOnly } else { $full }
$total = $files.Count
$i = 0
$failures = New-Object System.Collections.Generic.List[string]

try {
    New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
    $logDir = Split-Path -Parent $LogFile
    if ($logDir) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
} catch {
    Write-Host "ERROR: could not create folders: $($_.Exception.Message)"
    Write-Log "mkdir failed: $($_.Exception.Message)" "ERROR"
    exit 10
}

Write-Log "begin DestRoot=$DestRoot RawBase=$RawBase Manifest=$Manifest count=$total"
Show-Status -StepLabel "[0/$total] preparing download" -Source $RawBase -Status "connecting..."

foreach ($rel in $files) {
    $i++
    $url = "$RawBase/$rel"
    $out = Join-Path $DestRoot ($rel -replace "/", "\")
    $outDir = Split-Path -Parent $out
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    }

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source "https://github.com/Otaconskeep/otacons-ai-ecosystem" `
        -Status "connecting..." -File $rel
    Write-Log "GET $url -> $out"

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source $url -Status "downloading..." -File $rel

    $ok = $false
    $errText = ""
    try {
        Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 120
        $ok = $true
    } catch {
        $errText = $_.Exception.Message
        Write-Log "Invoke-WebRequest failed: $errText" "ERROR"
        # Fallback: curl.exe (ships with Windows 10/11)
        $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
        if ($curl) {
            Write-Log "trying curl.exe fallback"
            Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
                -Source $url -Status "downloading (curl fallback)..." -File $rel
            $p = Start-Process -FilePath "curl.exe" -ArgumentList @(
                "-fsSL", "--connect-timeout", "20", "--max-time", "120",
                "-o", $out, $url
            ) -Wait -PassThru -NoNewWindow
            Write-Log "curl.exe exit=$($p.ExitCode)"
            if ($p.ExitCode -eq 0) { $ok = $true; $errText = "" }
            else { $errText = "curl.exe exit $($p.ExitCode); prior: $errText" }
        }
    }

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source $url -Status "verifying files..." -File $rel

    $minSize = if ($rel -like "*.ps1") { 40 } else { 40 }
    if (-not $ok -or -not (Test-Path $out) -or ((Get-Item $out).Length -lt $minSize)) {
        $len = if (Test-Path $out) { (Get-Item $out).Length } else { 0 }
        $msg = "failed $rel size=$len err=$errText"
        Write-Log $msg "ERROR"
        $failures.Add($msg)
        Write-Host "  FAILED: $rel" -ForegroundColor Red
        Write-Host "  $errText" -ForegroundColor Red
        # Continue trying remaining files so the log shows the full picture; still exit nonzero.
        continue
    }

    $len = (Get-Item $out).Length
    Write-Log "ok $rel bytes=$len"
    Write-Host "  OK: $rel ($len bytes)" -ForegroundColor Green
}

if ($failures.Count -gt 0) {
    Write-Log "FETCH FAILED count=$($failures.Count)" "ERROR"
    Write-Host ""
    Write-Host "FETCH SUMMARY: $($failures.Count) file(s) failed" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" }
    exit 1
}

Write-Log "FETCH OK all $total files"
Write-Host ""
Write-Host "  All setup files downloaded." -ForegroundColor Green
exit 0
