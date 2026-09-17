# OtaconsKeep bootstrap file fetch - stdout/stderr + exit codes for the BAT wrapper.
# No git. Safe to re-run. Does not store credentials.
#
# ROOT CAUSE FIX: never overwrite the running bootstrap-fetch.ps1 via -OutFile.
# powershell -File keeps that path open; rewriting it fails on Windows -> exit 1
# even when the on-disk helper is already valid.

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

# Win11/PS 5.1: GitHub requires TLS 1.2; session default can still be too weak on some images.
try {
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.SecurityProtocolType]::Tls12 -bor `
        [Net.SecurityProtocolType]::Tls11 -bor `
        [Net.SecurityProtocolType]::Tls
} catch {}

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

function Get-NormalizedPath {
    param([string]$Path)
    if (-not $Path) { return "" }
    try {
        if (Test-Path -LiteralPath $Path) {
            return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
        }
        return [System.IO.Path]::GetFullPath($Path)
    } catch {
        return $Path
    }
}

# Do NOT list bootstrap-fetch.ps1 here when this script is already running from that path.
# Re-fetching the running script overwrites a locked file on Windows -> exit code 1.
$full = @(
    "install_otacon.bat",
    "OtaconsKeep-Setup.bat",
    "install_otacon.sh",
    "release.json",
    "deploy/installer-revision.txt",
    "deploy/windows-setup-assistant.ps1",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/wake-otacon.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1"
)
$deployOnly = @(
    "install_otacon.sh",
    "release.json",
    "deploy/installer-revision.txt",
    "deploy/windows-setup-assistant.ps1",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/wake-otacon.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1"
)

$files = if ($Manifest -eq "deploy") { $deployOnly } else { $full }
$total = $files.Count
$i = 0
$failures = New-Object System.Collections.Generic.List[string]
$lastErrorBlock = New-Object System.Collections.Generic.List[string]

$selfPath = ""
try { $selfPath = Get-NormalizedPath $MyInvocation.MyCommand.Path } catch {}

try {
    New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
    $logDir = Split-Path -Parent $LogFile
    if ($logDir) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
} catch {
    Write-Host "ERROR: could not create folders: $($_.Exception.Message)"
    Write-Log "mkdir failed: $($_.Exception.Message)" "ERROR"
    exit 10
}

Write-Log "begin DestRoot=$DestRoot RawBase=$RawBase Manifest=$Manifest count=$total self=$selfPath"
Write-Log "env=Windows cwd=$(Get-Location) ps=$($PSVersionTable.PSVersion) tls=$([Net.ServicePointManager]::SecurityProtocol)"
Show-Status -StepLabel "[0/$total] preparing download" -Source $RawBase -Status "connecting..."

function Save-FileDownload {
    param(
        [string]$Url,
        [string]$OutPath,
        [string]$Rel
    )
    $tmp = "$OutPath.otacon-download"
    $errParts = New-Object System.Collections.Generic.List[string]

    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

    # Prefer curl.exe first (Schannel; reliable on clean Win11). Fall back to Invoke-WebRequest.
    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    if ($curl) {
        Write-Log "curl.exe GET $Url"
        if ($DebugMode) {
            Write-Host "[DEBUG] env=Windows cwd=$(Get-Location)"
            Write-Host "[DEBUG] command=curl.exe -fsSL --connect-timeout 20 --max-time 120 -o `"$tmp`" `"$Url`""
        }
        $p = Start-Process -FilePath "curl.exe" -ArgumentList @(
            "-fsSL", "--connect-timeout", "20", "--max-time", "120",
            "-o", $tmp, $Url
        ) -Wait -PassThru -NoNewWindow
        $code = $p.ExitCode
        Write-Log "curl.exe exit=$code for $Rel"
        if ($DebugMode) { Write-Host "[DEBUG] errorlevel=$code" }
        if ($code -eq 0 -and (Test-Path -LiteralPath $tmp) -and ((Get-Item -LiteralPath $tmp).Length -ge 40)) {
            Move-Item -LiteralPath $tmp -Destination $OutPath -Force
            return @{ Ok = $true; Error = ""; Method = "curl.exe" }
        }
        $errParts.Add("curl.exe exit $code")
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    } else {
        Write-Log "curl.exe not found" "WARN"
        $errParts.Add("curl.exe not found")
    }

    try {
        Write-Log "Invoke-WebRequest GET $Url"
        if ($DebugMode) {
            Write-Host "[DEBUG] command=Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing"
        }
        Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing -TimeoutSec 120
        if ((Test-Path -LiteralPath $tmp) -and ((Get-Item -LiteralPath $tmp).Length -ge 40)) {
            Move-Item -LiteralPath $tmp -Destination $OutPath -Force
            return @{ Ok = $true; Error = ""; Method = "Invoke-WebRequest" }
        }
        $errParts.Add("Invoke-WebRequest wrote missing/small file")
    } catch {
        $msg = $_.Exception.Message
        Write-Log "Invoke-WebRequest failed: $msg" "ERROR"
        $errParts.Add($msg)
        $lastErrorBlock.Add("$Rel : $msg")
    }

    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    return @{ Ok = $false; Error = ($errParts -join " | "); Method = "none" }
}

foreach ($rel in $files) {
    $i++
    $url = "$RawBase/$rel"
    $out = Join-Path $DestRoot ($rel -replace "/", [IO.Path]::DirectorySeparatorChar)
    $outFull = Get-NormalizedPath $out
    $outDir = Split-Path -Parent $out
    if (-not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    }

    # Skip overwriting the running script (file lock -> false failure on Windows).
    if ($selfPath -and $outFull -and ($selfPath -eq $outFull)) {
        Write-Log "skip self-overwrite $rel (running script)"
        Write-Host "  SKIP (already running): $rel" -ForegroundColor DarkYellow
        continue
    }

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source "https://github.com/Otaconskeep/otacons-ai-ecosystem" `
        -Status "connecting..." -File $rel
    Write-Log "GET $url -> $out"

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source $url -Status "downloading..." -File $rel

    $result = Save-FileDownload -Url $url -OutPath $out -Rel $rel

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source $url -Status "verifying files..." -File $rel

    if (-not $result.Ok -or -not (Test-Path -LiteralPath $out) -or ((Get-Item -LiteralPath $out).Length -lt 40)) {
        $len = if (Test-Path -LiteralPath $out) { (Get-Item -LiteralPath $out).Length } else { 0 }
        $msg = "failed $rel size=$len method=$($result.Method) err=$($result.Error)"
        Write-Log $msg "ERROR"
        $failures.Add($msg)
        $lastErrorBlock.Add($msg)
        Write-Host "  FAILED: $rel" -ForegroundColor Red
        Write-Host "  $($result.Error)" -ForegroundColor Red
        continue
    }

    $len = (Get-Item -LiteralPath $out).Length
    Write-Log "ok $rel bytes=$len method=$($result.Method)"
    Write-Host "  OK: $rel ($len bytes) via $($result.Method)" -ForegroundColor Green
}

if ($failures.Count -gt 0) {
    Write-Log "FETCH FAILED count=$($failures.Count)" "ERROR"
    Write-Host ""
    Write-Host "FETCH SUMMARY: $($failures.Count) file(s) failed" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" }
    # Machine-readable trailer for the BAT failure screen
    Write-Host ""
    Write-Host "OTACON_FETCH_FAILED"
    Write-Host "FAILED_COMMAND=download otaconskeep setup files from github raw"
    Write-Host "EXIT_CODE=1"
    Write-Host ("LAST_ERROR=" + (($lastErrorBlock | Select-Object -Last 3) -join " ;; "))
    exit 1
}

Write-Log "FETCH OK all requested files"
Write-Host ""
Write-Host "  All setup files downloaded." -ForegroundColor Green
exit 0
