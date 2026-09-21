# OtaconsKeep Remote Support — shared helpers (owner builder + friend bootstrap).
# Designed & Engineered by Antonio G. Garcia // Otaconskeep
# Safe to dot-source from tests. No network side effects in pure helpers.

Set-StrictMode -Version Latest

function Get-OtaconBanner {
    return @'

 ============================================================
      ___  _                         _  __
     / _ \| |_ __ _  ___ ___  _ __  | |/ /___  ___ _ __
    | | | | __/ _` |/ __/ _ \| '_ \ | ' // _ \/ _ \ '_ \
    | |_| | || (_| | (_| (_) | | | || . \  __/  __/ |_) |
     \___/ \__\__,_|\___\___/|_| |_|_|\_\___|\___| .__/
                                                 |_|
                    OTACONS KEEP
              Remote Support Bootstrap
 ------------------------------------------------------------
   Don't worry — Otacon's got your back.
   If something stalls, leave this window open and tell Xof.
 ============================================================

'@
}

function Test-OtaconSshPublicKeyLine {
    param([Parameter(Mandatory = $true)][string]$Line)
    $t = $Line.Trim()
    if ([string]::IsNullOrWhiteSpace($t)) { return $false }
    if ($t.StartsWith('-----BEGIN ')) { return $false }
    return [bool]($t -match '^(ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|ssh-rsa)\s+\S+')
}

function Find-OtaconSshPublicKeyPath {
    param(
        [string]$HomeDir = $env:USERPROFILE,
        [string[]]$Names = @('id_ed25519.pub', 'id_ecdsa.pub', 'id_rsa.pub')
    )
    if ([string]::IsNullOrWhiteSpace($HomeDir)) { return $null }
    $sshDir = Join-Path $HomeDir '.ssh'
    foreach ($n in $Names) {
        if ($n -notlike '*.pub') { continue } # never consider private key filenames
        $p = Join-Path $sshDir $n
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $raw = Get-Content -LiteralPath $p -Raw -ErrorAction SilentlyContinue
        if (-not $raw) { continue }
        $line = ($raw -split "`r?`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
        if (Test-OtaconSshPublicKeyLine -Line $line) { return $p }
    }
    return $null
}

function Read-OtaconSshPublicKey {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path -notlike '*.pub') {
        throw "Refusing to read non-.pub path: $Path"
    }
    # Block private key basenames even if somehow renamed weirdly
    $base = [IO.Path]::GetFileName($Path).ToLowerInvariant()
    foreach ($bad in @('id_ed25519', 'id_ecdsa', 'id_rsa', 'id_dsa')) {
        if ($base -eq $bad) { throw "Refusing to open private key filename: $base" }
    }
    $raw = Get-Content -LiteralPath $Path -Raw
    $line = ($raw -split "`r?`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1).Trim()
    if (-not (Test-OtaconSshPublicKeyLine -Line $line)) {
        throw "Unrecognized SSH public key format in $Path"
    }
    return $line
}

function Protect-OtaconSecretText {
    param(
        [AllowNull()][string]$Text,
        [string[]]$Secrets = @()
    )
    if ($null -eq $Text) { return '' }
    $out = [string]$Text
    foreach ($s in $Secrets) {
        if ([string]::IsNullOrWhiteSpace($s)) { continue }
        if ($s.Length -ge 8) {
            $out = $out.Replace($s, '<REDACTED>')
        }
    }
    # Heuristic: Tailscale auth keys
    $out = [regex]::Replace($out, 'tskey-[A-Za-z0-9_-]+', '<REDACTED>')
    return $out
}

function ConvertTo-OtaconSafeAlias {
    param([Parameter(Mandatory = $true)][string]$Name)
    $n = $Name.Trim().ToLowerInvariant()
    $n = [regex]::Replace($n, '[^a-z0-9-]+', '-')
    $n = [regex]::Replace($n, '-{2,}', '-').Trim('-')
    if ([string]::IsNullOrWhiteSpace($n)) { $n = 'friend' }
    if ($n -notlike 'otacon-*') { $n = "otacon-$n" }
    return $n
}

function Add-OtaconAuthorizedKeyLine {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$ExistingContent,
        [Parameter(Mandatory = $true)][string]$PublicKeyLine
    )
    $want = $PublicKeyLine.Trim()
    if (-not (Test-OtaconSshPublicKeyLine -Line $want)) {
        throw 'Refusing to append non-public-key content'
    }
    $lines = @()
    if (-not [string]::IsNullOrWhiteSpace($ExistingContent)) {
        $lines = @($ExistingContent -split "`r?`n" | ForEach-Object { $_.TrimEnd() } | Where-Object { $_ -ne '' })
    }
    $already = 0
    foreach ($l in $lines) {
        if ($l.Trim() -eq $want) { $already++ }
    }
    if ($already -gt 0) {
        $joined = ($lines -join "`n").TrimEnd() + "`n"
        return @{ Content = $joined; Added = $false; Count = [int]$already }
    }
    $lines += $want
    $joined = ($lines -join "`n").TrimEnd() + "`n"
    return @{ Content = $joined; Added = $true; Count = 1 }
}

function Merge-OtaconSshdConfigLine {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigText,
        [Parameter(Mandatory = $true)][string]$Directive,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $target = "$Directive $Value"
    $lines = New-Object System.Collections.Generic.List[string]
    $seen = $false
    foreach ($raw in ($ConfigText -split "`r?`n")) {
        if ($raw -match ('^\s*' + [regex]::Escape($Directive) + '\s+')) {
            if (-not $seen) {
                $lines.Add($target) | Out-Null
                $seen = $true
            }
            # drop duplicates
            continue
        }
        $lines.Add($raw) | Out-Null
    }
    if (-not $seen) { $lines.Add($target) | Out-Null }
    return (($lines -join "`n").TrimEnd() + "`n")
}

function Test-OtaconPrivateKeyLeak {
    param([Parameter(Mandatory = $true)][string]$Text)
    if ($Text -match '-----BEGIN (OPENSSH |RSA |EC )?PRIVATE KEY-----') { return $true }
    if ($Text -match '(?m)^-----BEGIN .*PRIVATE KEY-----') { return $true }
    return $false
}

function New-OtaconRemoteBatWrapper {
    param(
        [Parameter(Mandatory = $true)][string]$EmbeddedPs1,
        [Parameter(Mandatory = $true)][string]$Recipient
    )
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($EmbeddedPs1))
    $safeRecip = ($Recipient -replace '[^\w\- ]', '').Trim()
    if ([string]::IsNullOrWhiteSpace($safeRecip)) { $safeRecip = 'Friend' }

    # Single-quoted extract so PowerShell does not expand $p/$c/$b64 while building the BAT.
    $extract = @'
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%~f0'; $c=Get-Content -LiteralPath $p -Raw; $m=[regex]::Match($c,'(?s)___OTACON_PAYLOAD_B64_BEGIN___\r?\n(.+?)\r?\n___OTACON_PAYLOAD_B64_END___'); if(-not $m.Success){Write-Host '[FAIL] payload missing'; exit 2}; $b64=($m.Groups[1].Value -replace '\s',''); [IO.File]::WriteAllBytes($env:OTACON_RS_PS1,[Convert]::FromBase64String($b64)); exit 0"
'@

    $nl = "`r`n"
    $parts = @(
        '@echo off',
        'REM ============================================================',
        "REM  OtaconsKeep Remote Support Setup - $safeRecip",
        'REM  Right-click -> Run as administrator. Do not close this window.',
        'REM  Designed by Antonio G. Garcia // Otaconskeep',
        'REM ============================================================',
        'setlocal EnableExtensions',
        "title OtaconsKeep Remote Support - $safeRecip",
        '',
        'net session >nul 2>&1',
        'if errorlevel 1 (',
        '  echo.',
        '  echo  This installer needs Administrator.',
        '  echo  Right-click this file and choose: Run as administrator',
        '  echo.',
        '  pause',
        '  exit /b 1',
        ')',
        '',
        'set "OTACON_RS_DIR=%LOCALAPPDATA%\OtaconsKeep\remote-support"',
        'if not exist "%OTACON_RS_DIR%" mkdir "%OTACON_RS_DIR%" >nul 2>&1',
        'set "OTACON_RS_PS1=%OTACON_RS_DIR%\bootstrap-run.ps1"',
        '',
        $extract,
        '',
        'if errorlevel 1 (',
        '  echo [FAIL] Could not materialize bootstrap script.',
        '  pause',
        '  exit /b 1',
        ')',
        '',
        'powershell -NoProfile -ExecutionPolicy Bypass -File "%OTACON_RS_PS1%" %*',
        'set "EC=%ERRORLEVEL%"',
        'del /f /q "%OTACON_RS_PS1%" >nul 2>&1',
        'echo.',
        'echo  This window will stay open. Press a key to exit.',
        'pause >nul',
        'exit /b %EC%',
        '',
        'goto :eof',
        '___OTACON_PAYLOAD_B64_BEGIN___',
        $b64,
        '___OTACON_PAYLOAD_B64_END___',
        ''
    )
    return ($parts -join $nl)
}

# Dot-sourced by builder/tests — Export-ModuleMember only when imported as module.
if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function * -ErrorAction SilentlyContinue
}
