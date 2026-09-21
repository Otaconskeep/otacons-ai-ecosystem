# OtaconsKeep bootstrap file fetch - stdout/stderr + exit codes for the BAT wrapper.
# No git. Safe to re-run. Does not store credentials.
#
# Installer-owned files are NOT valid just because they exist.
# They are valid only when they match the expected release/version/hash.
#
# ROOT CAUSE FIX: never overwrite the running bootstrap-fetch.ps1 via -OutFile.
# powershell -File keeps that path open; rewriting it fails on Windows -> exit 1
# even when the on-disk helper is already valid. The public launcher MUST refresh
# this script BEFORE invoking it (atomic temp download + replace).

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

function Get-FileSha256Hex {
    param([string]$Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            $hash = $sha.ComputeHash($fs)
        } finally { $fs.Dispose() }
        return ([BitConverter]::ToString($hash) -replace "-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

# Hardcoded complete manifest (source of truth if release.json is incomplete).
# Do NOT list bootstrap-fetch.ps1 here when this script is already running from that path.
$full = @(
    "install_otacon.bat",
    "OtaconsKeep-Setup.bat",
    "OtaconExpansion-Setup.bat",
    "Reinstall-Otacon.bat",
    "Fix-Otacon-GPU.bat",
    "install_otacon.sh",
    "install_otacon_expansion.sh",
    "release.json",
    "deploy/installer-revision.txt",
    "deploy/windows-setup-assistant.ps1",
    "deploy/repair-otacon-core.ps1",
    "deploy/install-otacon-expansion.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/fix-otacon-gpu.ps1",
    "deploy/get-fix-codec.cmd",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/install-desktop-launcher.ps1",
    "deploy/otacon-launcher.ico",
    "deploy/wake-otacon.ps1",
    "deploy/keep-ubuntu-awake.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1"
)
$deployOnly = @(
    "install_otacon.sh",
    "install_otacon_expansion.sh",
    "release.json",
    "deploy/installer-revision.txt",
    "deploy/windows-setup-assistant.ps1",
    "deploy/repair-otacon-core.ps1",
    "deploy/install-otacon-expansion.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/fix-otacon-gpu.ps1",
    "deploy/get-fix-codec.cmd",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/install-desktop-launcher.ps1",
    "deploy/otacon-launcher.ico",
    "deploy/wake-otacon.ps1",
    "deploy/keep-ubuntu-awake.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1"
)

$files = if ($Manifest -eq "deploy") { $deployOnly } else { $full }
$hashByPath = @{}
$bundleVersion = ""
$bundleCommit = ""
$bundleRef = ""

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

Write-Log "begin DestRoot=$DestRoot RawBase=$RawBase Manifest=$Manifest count=$($files.Count) self=$selfPath"
Write-Log "env=Windows cwd=$(Get-Location) ps=$($PSVersionTable.PSVersion) tls=$([Net.ServicePointManager]::SecurityProtocol)"
Show-Status -StepLabel "[0/$($files.Count)] preparing download" -Source $RawBase -Status "connecting..."

function Save-FileDownload {
    param(
        [string]$Url,
        [string]$OutPath,
        [string]$Rel,
        [string]$ExpectedSha256 = ""
    )
    $tmp = "$OutPath.otacon-download"
    $errParts = New-Object System.Collections.Generic.List[string]

    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

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
            if ($ExpectedSha256) {
                $got = Get-FileSha256Hex -Path $tmp
                if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
                    $errParts.Add("sha256 mismatch expected=$ExpectedSha256 got=$got")
                    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                    return @{ Ok = $false; Error = ($errParts -join " | "); Method = "curl.exe"; Replaced = $false; Sha256 = $got }
                }
            }
            Move-Item -LiteralPath $tmp -Destination $OutPath -Force
            $sha = Get-FileSha256Hex -Path $OutPath
            return @{ Ok = $true; Error = ""; Method = "curl.exe"; Replaced = $true; Sha256 = $sha }
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
            if ($ExpectedSha256) {
                $got = Get-FileSha256Hex -Path $tmp
                if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
                    $errParts.Add("sha256 mismatch expected=$ExpectedSha256 got=$got")
                    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                    return @{ Ok = $false; Error = ($errParts -join " | "); Method = "Invoke-WebRequest"; Replaced = $false; Sha256 = $got }
                }
            }
            Move-Item -LiteralPath $tmp -Destination $OutPath -Force
            $sha = Get-FileSha256Hex -Path $OutPath
            return @{ Ok = $true; Error = ""; Method = "Invoke-WebRequest"; Replaced = $true; Sha256 = $sha }
        }
        $errParts.Add("Invoke-WebRequest wrote missing/small file")
    } catch {
        $msg = $_.Exception.Message
        Write-Log "Invoke-WebRequest failed: $msg" "ERROR"
        $errParts.Add($msg)
    }

    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    return @{ Ok = $false; Error = ($errParts -join " | "); Method = "none"; Replaced = $false; Sha256 = "" }
}

# --- Load release.json first (versioned installer bundle) ---
$branchRawBase = $RawBase
$releaseRel = "release.json"
$releaseUrl = "$RawBase/$releaseRel"
$releaseOut = Join-Path $DestRoot $releaseRel
Show-Status -StepLabel "[meta] release.json" -Source $releaseUrl -Status "downloading..." -File $releaseRel
$relResult = Save-FileDownload -Url $releaseUrl -OutPath $releaseOut -Rel $releaseRel
if ($relResult.Ok) {
    try {
        $relJson = Get-Content -LiteralPath $releaseOut -Raw -Encoding UTF8 | ConvertFrom-Json
        $bundleVersion = [string]$relJson.installer_version
        $bundleCommit = [string]$relJson.commit
        $bundleRef = [string]$relJson.ecosystem_ref
        if (-not $bundleRef) { $bundleRef = "main" }
        Write-Log "bundle installer_version=$bundleVersion commit=$bundleCommit ref=$bundleRef"
        Write-Host ("  INSTALLER_BUNDLE version={0} commit={1} ref={2}" -f $bundleVersion, $bundleCommit, $bundleRef) -ForegroundColor Cyan
        if ($relJson.files) {
            foreach ($entry in $relJson.files) {
                if ($entry.path -and $entry.sha256) {
                    $hashByPath[[string]$entry.path] = ([string]$entry.sha256).ToLowerInvariant()
                }
            }
            Write-Log ("release.json hashes loaded count={0}" -f $hashByPath.Count)
        }
        # Never SHA-pin branch-tip-only files (EOL-safe commit pin does not apply to these).
        if ($hashByPath.ContainsKey("deploy/installer-revision.txt")) { $hashByPath.Remove("deploy/installer-revision.txt") }
        if ($hashByPath.ContainsKey("release.json")) { $hashByPath.Remove("release.json") }
        if ($hashByPath.ContainsKey("deploy/bootstrap-fetch.ps1")) { $hashByPath.Remove("deploy/bootstrap-fetch.ps1") }
        # Prefer release.json file list when present (still force-include required helpers).
        if ($relJson.files -and $relJson.files.Count -gt 0) {
            $fromRelease = @()
            foreach ($entry in $relJson.files) {
                $p = [string]$entry.path
                if (-not $p) { continue }
                if ($p -eq "deploy/bootstrap-fetch.ps1") { continue } # refreshed by launcher, not self
                if ($Manifest -eq "deploy") {
                    if ($p -like "deploy/*" -or $p -eq "install_otacon.sh" -or $p -eq "install_otacon_expansion.sh" -or $p -eq "OtaconExpansion-Setup.bat" -or $p -eq "release.json" -or $p -eq "deploy/installer-revision.txt") {
                        $fromRelease += $p
                    }
                } else {
                    $fromRelease += $p
                }
            }
            foreach ($must in @(
                "release.json",
                "deploy/installer-revision.txt",
                "deploy/windows-setup-assistant.ps1",
                "deploy/repair-otacon-core.ps1",
                "deploy/wsl-bash-file.ps1"
            )) {
                if ($fromRelease -notcontains $must) { $fromRelease += $must }
            }
            if ($fromRelease.Count -gt 0) { $files = $fromRelease | Select-Object -Unique }
        }
        # Pin downloads to the commit that owns the hashed blobs.
        # Branch-name raw URLs (e.g. /main/) can normalize CRLF->LF and break SHA256.
        if ($bundleCommit -match '^[0-9a-fA-F]{7,40}$') {
            if ($RawBase -match '^(https?://raw\.githubusercontent\.com/[^/]+/[^/]+/)([^/]+)/?$') {
                $RawBase = $Matches[1] + $bundleCommit.ToLowerInvariant()
                Write-Log "pin RawBase to commit for exact blob bytes: $RawBase (was $branchRawBase)"
                Write-Host ("  RAW_PIN commit={0}" -f $bundleCommit) -ForegroundColor Cyan
            }
        }
    } catch {
        Write-Log ("release.json parse warn: {0}" -f $_.Exception.Message) "WARN"
    }
} else {
    Write-Log ("release.json download failed (continuing with hardcoded manifest): {0}" -f $relResult.Error) "WARN"
}

# Always refresh Linux sync pin from branch tip (not commit-pinned / not hashed).
$revRel = "deploy/installer-revision.txt"
$revOut = Join-Path $DestRoot ($revRel -replace "/", [IO.Path]::DirectorySeparatorChar)
$revUrl = "$branchRawBase/$revRel"
$revResult = Save-FileDownload -Url $revUrl -OutPath $revOut -Rel $revRel
if ($revResult.Ok) {
    Write-Log ("installer-revision.txt from branch tip ok sha={0}" -f $revResult.Sha256)
} else {
    Write-Log ("installer-revision.txt branch tip download warn: {0}" -f $revResult.Error) "WARN"
}

$failures = New-Object System.Collections.Generic.List[string]
$lastErrorBlock = New-Object System.Collections.Generic.List[string]
$replaced = New-Object System.Collections.Generic.List[string]
$total = $files.Count
$i = 0

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
        Write-Log "skip self-overwrite $rel (running script; launcher must have refreshed it)"
        Write-Host "  SKIP (already running): $rel" -ForegroundColor DarkYellow
        continue
    }

    # NEVER skip because a cached file already exists.
    $expected = ""
    if ($hashByPath.ContainsKey($rel)) { $expected = [string]$hashByPath[$rel] }

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source "https://github.com/Otaconskeep/otacons-ai-ecosystem" `
        -Status "connecting..." -File $rel
    Write-Log "GET $url -> $out (always replace; expected_sha=$expected)"

    Show-Status -StepLabel ("[{0}/{1}] downloading otaconskeep files" -f $i, $total) `
        -Source $url -Status "downloading..." -File $rel

    $result = Save-FileDownload -Url $url -OutPath $out -Rel $rel -ExpectedSha256 $expected

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
    $replaced.Add($rel)
    Write-Log ("ok $rel bytes=$len method={0} sha256={1} replaced=1" -f $result.Method, $result.Sha256)
    Write-Host ("  OK: {0} ({1} bytes) sha={2} via {3}" -f $rel, $len, $result.Sha256.Substring(0, [Math]::Min(12, $result.Sha256.Length)), $result.Method) -ForegroundColor Green

    # ONLY AFTER successful hash verification may local encoding normalization occur.
    # Manifest sha256 describes exact published/download bytes; post-normalize hash may differ.
    if ($rel -like "*.ps1") {
        try {
            $bytes = [System.IO.File]::ReadAllBytes($out)
            $preHash = Get-FileSha256Hex -Path $out
            $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
            $text = if ($hasBom) {
                [System.Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
            } else {
                [System.Text.Encoding]::UTF8.GetString($bytes)
            }
            $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
            $text = $text -replace "`n", "`r`n"
            $utf8Bom = New-Object System.Text.UTF8Encoding $true
            [System.IO.File]::WriteAllText($out, $text, $utf8Bom)
            $postHash = Get-FileSha256Hex -Path $out
            Write-Log "normalized encoding BOM+CRLF $rel (post-verify; pre=$preHash post=$postHash)"
        } catch {
            Write-Log "encoding normalize skipped $rel : $($_.Exception.Message)" "WARN"
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Log "FETCH FAILED count=$($failures.Count)" "ERROR"
    Write-Host ""
    Write-Host "FETCH SUMMARY: $($failures.Count) file(s) failed" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" }
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

# Required helpers - missing these caused "Windows updated, Linux app did not".
$required = @(
    "deploy/windows-setup-assistant.ps1",
    "deploy/repair-otacon-core.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/installer-revision.txt",
    "install_otacon.bat",
    "install_otacon.sh"
)
$missingReq = New-Object System.Collections.Generic.List[string]
foreach ($rel in $required) {
    if ($Manifest -eq "deploy" -and ($rel -eq "install_otacon.bat")) { continue }
    $p = Join-Path $DestRoot ($rel -replace "/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $p) -or ((Get-Item -LiteralPath $p).Length -lt 40)) {
        $missingReq.Add($rel)
        Write-Host "  MISSING REQUIRED: $rel" -ForegroundColor Red
    }
}
if ($missingReq.Count -gt 0) {
    Write-Log "FETCH FAILED required missing=$($missingReq -join ',')" "ERROR"
    Write-Host "OTACON_FETCH_FAILED"
    Write-Host "FAILED_COMMAND=verify required installer helpers present"
    Write-Host "EXIT_CODE=1"
    Write-Host ("LAST_ERROR=missing required files: " + ($missingReq -join ", "))
    exit 1
}
Write-Log "required helpers present including repair-otacon-core.ps1 and wsl-bash-file.ps1"

# Prove the INSTALLED repair helper is the temp-.sh transport (not stale bash -lc).
$repairPath = Join-Path $DestRoot ("deploy/repair-otacon-core.ps1" -replace "/", [IO.Path]::DirectorySeparatorChar)
$repairText = Get-Content -LiteralPath $repairPath -Raw -Encoding UTF8
if ($repairText -match 'bash -lc \$bash') {
    Write-Log "INSTALLED repair still has bash -lc `$bash - stale cache" "ERROR"
    Write-Host "  STALE repair-otacon-core.ps1 still uses bash -lc `$bash" -ForegroundColor Red
    Write-Host "OTACON_FETCH_FAILED"
    Write-Host "FAILED_COMMAND=verify installed repair-otacon-core.ps1 uses temp .sh transport"
    Write-Host "EXIT_CODE=1"
    Write-Host "LAST_ERROR=installed repair helper is stale (bash -lc `$bash)"
    exit 1
}
if ($repairText -notmatch 'Invoke-OtaconWslBashFile') {
    Write-Log "INSTALLED repair missing Invoke-OtaconWslBashFile" "ERROR"
    Write-Host "  INSTALLED repair-otacon-core.ps1 missing Invoke-OtaconWslBashFile" -ForegroundColor Red
    Write-Host "OTACON_FETCH_FAILED"
    Write-Host "FAILED_COMMAND=verify installed repair-otacon-core.ps1 uses Invoke-OtaconWslBashFile"
    Write-Host "EXIT_CODE=1"
    Write-Host "LAST_ERROR=installed repair helper missing file transport"
    exit 1
}
Write-Log "installed repair helper uses Invoke-OtaconWslBashFile (temp .sh transport)"

$wslHelper = Join-Path $DestRoot ("deploy/wsl-bash-file.ps1" -replace "/", [IO.Path]::DirectorySeparatorChar)
$wslText = Get-Content -LiteralPath $wslHelper -Raw -Encoding UTF8
if ($wslText -notmatch 'function Invoke-OtaconWslBashFile') {
    Write-Log "wsl-bash-file.ps1 missing Invoke-OtaconWslBashFile" "ERROR"
    Write-Host "OTACON_FETCH_FAILED"
    Write-Host "FAILED_COMMAND=verify deploy/wsl-bash-file.ps1"
    Write-Host "EXIT_CODE=1"
    Write-Host "LAST_ERROR=wsl-bash-file.ps1 incomplete"
    exit 1
}

# Parse-check critical helpers under this host's PowerShell before Setup continues.
$parseTargets = @(
    "deploy/repair-otacon-core.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/windows-setup-assistant.ps1",
    "deploy/fix-otacon-gpu.ps1"
)
foreach ($rel in $parseTargets) {
    $p = Join-Path $DestRoot ($rel -replace "/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $tokens = $null
    $errs = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) {
        $msg = "parse failed $rel : " + (($errs | ForEach-Object { $_.Message }) -join " | ")
        Write-Log $msg "ERROR"
        Write-Host "  PARSE FAILED: $rel" -ForegroundColor Red
        Write-Host "OTACON_FETCH_FAILED"
        Write-Host "FAILED_COMMAND=PowerShell 5.1 parse check for $rel"
        Write-Host "EXIT_CODE=1"
        Write-Host "LAST_ERROR=$msg"
        exit 1
    }
    Write-Log "parse ok $rel"
}

# Persist local pin + refresh log.
$pinPath = Join-Path $DestRoot ("deploy/installer-bundle.pin.json" -replace "/", [IO.Path]::DirectorySeparatorChar)
$revPath = Join-Path $DestRoot ("deploy/installer-revision.txt" -replace "/", [IO.Path]::DirectorySeparatorChar)
$revText = ""
if (Test-Path -LiteralPath $revPath) {
    $revText = (Get-Content -LiteralPath $revPath -Raw -Encoding UTF8).Trim()
}
if (-not $bundleCommit -and $revText) { $bundleCommit = $revText }
$pinObj = @{
    installer_version = $bundleVersion
    commit            = $bundleCommit
    ecosystem_ref     = $bundleRef
    raw_base          = $RawBase
    refreshed_utc     = (Get-Date).ToUniversalTime().ToString("o")
    files_replaced    = @($replaced)
}
try {
    ($pinObj | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $pinPath -Encoding UTF8
    Write-Log "wrote pin $pinPath version=$bundleVersion commit=$bundleCommit replaced=$($replaced.Count)"
} catch {
    Write-Log ("pin write warn: {0}" -f $_.Exception.Message) "WARN"
}

Write-Host ""
Write-Host ("  BOOTSTRAP_OK version={0} commit={1} ref={2} replaced={3}" -f $bundleVersion, $bundleCommit, $bundleRef, $replaced.Count) -ForegroundColor Green
Write-Log ("BOOTSTRAP_OK version={0} commit={1} ref={2} replaced={3}" -f $bundleVersion, $bundleCommit, $bundleRef, $replaced.Count)
exit 0
