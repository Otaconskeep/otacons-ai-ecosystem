# OtaconsKeep Remote Support — friend bootstrap (templated).
# Placeholders replaced by Build-RemoteSupportInstaller.ps1:
#   {{RECIPIENT}} {{ALIAS}} {{SSH_USER}} {{SSH_PUBKEY}} {{TS_AUTH_KEY}}
# Designed & Engineered by Antonio G. Garcia // Otaconskeep

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OtaconRecipient = '{{RECIPIENT}}'
$OtaconAlias = '{{ALIAS}}'
$OtaconSshUser = '{{SSH_USER}}'
$OtaconSshPubKey = '{{SSH_PUBKEY}}'
$OtaconTsAuthKey = '{{TS_AUTH_KEY}}'

$script:DryRun = $false
$script:Secrets = @($OtaconTsAuthKey)
$script:Gates = [ordered]@{}
$script:LogPath = 'C:\ProgramData\OtaconsKeep\logs\remote-support-setup.log'
$script:InfoPath = Join-Path $env:USERPROFILE 'Desktop\OtaconsKeep-Remote-Info.txt'
$script:TailscaleIp = ''
$script:TailscaleExe = $null

foreach ($a in $args) {
    if ($a -eq '-DryRun' -or $a -eq '--dry-run' -or $a -eq '/dryrun') { $script:DryRun = $true }
}

function Protect-Text([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $out = $Text
    foreach ($s in $script:Secrets) {
        if ($s -and $s.Length -ge 8) { $out = $out.Replace($s, '<REDACTED>') }
    }
    return [regex]::Replace($out, 'tskey-[A-Za-z0-9_-]+', '<REDACTED>')
}

function Write-OtaconLog {
    param([string]$Level, [string]$Message)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[{0}] [{1}] {2}" -f $ts, $Level, (Protect-Text $Message)
    try {
        $dir = Split-Path -Parent $script:LogPath
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    } catch {}
    $color = 'Gray'
    if ($Level -eq 'PASS') { $color = 'Green' }
    elseif ($Level -eq 'FAIL') { $color = 'Red' }
    elseif ($Level -eq 'WARN') { $color = 'Yellow' }
    Write-Host ("[{0}] {1}" -f $Level, (Protect-Text $Message)) -ForegroundColor $color
}

function Set-Gate([string]$Name, [bool]$Ok, [string]$Detail = '') {
    $script:Gates[$Name] = $Ok
    if ($Ok) { Write-OtaconLog 'PASS' ("{0}{1}" -f $Name, $(if ($Detail) { ": $Detail" } else { '' })) }
    else { Write-OtaconLog 'FAIL' ("{0}{1}" -f $Name, $(if ($Detail) { ": $Detail" } else { '' })) }
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-Banner {
    Write-Host @'

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

function Find-TailscaleExe {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'Tailscale\tailscale.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Tailscale\tailscale.exe'),
        (Get-Command tailscale.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Invoke-Tailscale {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$TsArgs)
    if (-not $script:TailscaleExe) { throw 'tailscale.exe not located' }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:TailscaleExe
    $psi.Arguments = ($TsArgs -join ' ')
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [Diagnostics.Process]::Start($psi)
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return @{ ExitCode = $p.ExitCode; StdOut = $stdout; StdErr = $stderr }
}

function Get-TailscaleStatusJson {
    $r = Invoke-Tailscale 'status' '--json'
    if ($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.StdOut)) { return $null }
    try { return ($r.StdOut | ConvertFrom-Json) } catch { return $null }
}

function Install-TailscaleIfNeeded {
    $script:TailscaleExe = Find-TailscaleExe
    if ($script:TailscaleExe) {
        Set-Gate 'Tailscale installed' $true $script:TailscaleExe
        return
    }
    if ($script:DryRun) {
        Write-OtaconLog 'WARN' 'DryRun: would download + silent-install Tailscale MSI'
        Set-Gate 'Tailscale installed' $true 'DryRun'
        return
    }
    $msi = Join-Path $env:TEMP ('tailscale-setup-{0}.msi' -f [guid]::NewGuid().ToString('n'))
    $url = 'https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi'
    Write-OtaconLog 'INFO' 'Downloading official Tailscale Windows installer…'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing
    $args = "/i `"$msi`" /qn /norestart"
    $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList $args -Wait -PassThru
    Remove-Item -LiteralPath $msi -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $script:TailscaleExe = Find-TailscaleExe
    if (-not $script:TailscaleExe) {
        Set-Gate 'Tailscale installed' $false 'tailscale.exe still missing after MSI'
        return
    }
    Set-Gate 'Tailscale installed' $true
}

function Ensure-TailscaleEnrollment {
    if ($script:DryRun) {
        Set-Gate 'Tailscale backend' $true 'DryRun'
        Set-Gate 'Tailscale authenticated' $true 'DryRun'
        Set-Gate 'Tailscale hostname' $true $OtaconAlias
        Set-Gate 'Tailscale IPv4' $true '100.64.0.1'
        Set-Gate 'Tailscale unattended' $true 'DryRun'
        $script:TailscaleIp = '100.64.0.1'
        return
    }
    if (-not $script:TailscaleExe) {
        Set-Gate 'Tailscale backend' $false 'missing exe'
        return
    }

    $st = Get-TailscaleStatusJson
    $backend = $null
    if ($st) { $backend = [string]$st.BackendState }
    if ($backend) { Set-Gate 'Tailscale backend' ($backend -in @('Running', 'Starting', 'NeedsLogin')) $backend }
    else { Set-Gate 'Tailscale backend' $false 'no status json' }

    $alreadyAuth = $false
    $existingHost = $null
    $existingIp = $null
    if ($st -and $st.Self) {
        $existingHost = [string]$st.Self.HostName
        if (-not $existingHost) { $existingHost = [string]$st.Self.DNSName }
        if ($st.Self.TailscaleIPs) {
            $existingIp = @($st.Self.TailscaleIPs | Where-Object { $_ -like '100.*' } | Select-Object -First 1)
        }
        if ($backend -eq 'Running' -and $existingIp) { $alreadyAuth = $true }
    }

    if ($alreadyAuth) {
        $hostOk = ($existingHost -and ($existingHost.TrimEnd('.') -ieq $OtaconAlias -or $existingHost -like "$OtaconAlias.*"))
        if ($hostOk) {
            Write-OtaconLog 'INFO' "Reusing existing Tailscale enrollment as $OtaconAlias"
            $script:TailscaleIp = $existingIp
            Set-Gate 'Tailscale authenticated' $true
            Set-Gate 'Tailscale hostname' $true $existingHost
            Set-Gate 'Tailscale IPv4' $true $existingIp
            # Prefer unattended prefs if queryable
            $prefs = Invoke-Tailscale 'debug' 'prefs' 2>$null
            $unattended = $true
            Set-Gate 'Tailscale unattended' $unattended 'already enrolled'
            return
        }
        Write-OtaconLog 'WARN' "Machine already connected to Tailscale as '$existingHost' ($existingIp)."
        Write-OtaconLog 'WARN' 'Refusing to overwrite an unrelated Tailscale network. Setup incomplete.'
        Set-Gate 'Tailscale authenticated' $false 'unrelated existing tailnet — not destroyed'
        Set-Gate 'Tailscale hostname' $false "want $OtaconAlias have $existingHost"
        Set-Gate 'Tailscale IPv4' $false
        Set-Gate 'Tailscale unattended' $false
        return
    }

    if ([string]::IsNullOrWhiteSpace($OtaconTsAuthKey) -or $OtaconTsAuthKey -like '{{*}}') {
        Set-Gate 'Tailscale authenticated' $false 'auth key missing from installer'
        return
    }

    Write-OtaconLog 'INFO' "Enrolling Tailscale as $OtaconAlias (unattended)…"
    $up = Invoke-Tailscale 'up' "--auth-key=$OtaconTsAuthKey" '--unattended' "--hostname=$OtaconAlias" '--accept-dns=false'
    if ($up.ExitCode -ne 0) {
        Write-OtaconLog 'FAIL' ("tailscale up failed: " + (Protect-Text ($up.StdErr + ' ' + $up.StdOut)))
        Set-Gate 'Tailscale authenticated' $false 'tailscale up failed'
        return
    }

    Start-Sleep -Seconds 4
    $st2 = Get-TailscaleStatusJson
    $ip = $null
    $hn = $null
    if ($st2 -and $st2.Self) {
        $hn = [string]$st2.Self.HostName
        if ($st2.Self.TailscaleIPs) {
            $ip = @($st2.Self.TailscaleIPs | Where-Object { $_ -like '100.*' } | Select-Object -First 1)
        }
    }
    $script:TailscaleIp = $ip
    Set-Gate 'Tailscale authenticated' ($st2 -and $st2.BackendState -eq 'Running' -and $ip) ([string]$st2.BackendState)
    Set-Gate 'Tailscale hostname' ($hn -and ($hn.TrimEnd('.') -ieq $OtaconAlias -or $hn -like "$OtaconAlias.*")) $hn
    Set-Gate 'Tailscale IPv4' ([bool]$ip) $ip
    Set-Gate 'Tailscale unattended' $true 'requested via --unattended'
    Set-Gate 'Tailscale backend' ($st2 -and $st2.BackendState -eq 'Running') ([string]$st2.BackendState)
}

function Install-OpenSshServer {
    $capName = 'OpenSSH.Server~~~~0.0.1.0'
    $cap = Get-WindowsCapability -Online -Name $capName -ErrorAction SilentlyContinue
    if ($cap -and $cap.State -eq 'Installed') {
        Set-Gate 'OpenSSH installed' $true 'already present'
        return
    }
    if ($script:DryRun) {
        Write-OtaconLog 'WARN' 'DryRun: would Add-WindowsCapability OpenSSH.Server'
        Set-Gate 'OpenSSH installed' $true 'DryRun'
        return
    }
    Write-OtaconLog 'INFO' 'Installing Windows OpenSSH Server capability…'
    Add-WindowsCapability -Online -Name $capName | Out-Null
    $cap2 = Get-WindowsCapability -Online -Name $capName -ErrorAction SilentlyContinue
    Set-Gate 'OpenSSH installed' ($cap2 -and $cap2.State -eq 'Installed')
}

function Ensure-SshdService {
    if ($script:DryRun) {
        Set-Gate 'sshd exists' $true 'DryRun'
        Set-Gate 'sshd Running' $true 'DryRun'
        Set-Gate 'sshd Automatic' $true 'DryRun'
        return
    }
    $svc = Get-Service -Name sshd -ErrorAction SilentlyContinue
    Set-Gate 'sshd exists' ([bool]$svc)
    if (-not $svc) { return }
    if ($svc.StartType -ne 'Automatic') {
        Set-Service -Name sshd -StartupType Automatic
    }
    if ($svc.Status -ne 'Running') {
        Start-Service -Name sshd
        Start-Sleep -Seconds 2
        $svc = Get-Service -Name sshd
    }
    # Also ensure ssh-agent optional — not required
    Set-Gate 'sshd Running' ($svc.Status -eq 'Running') ([string]$svc.Status)
    $svc2 = Get-Service -Name sshd
    Set-Gate 'sshd Automatic' ($svc2.StartType -eq 'Automatic') ([string]$svc2.StartType)
}

function Install-OwnerPublicKey {
    $path = 'C:\ProgramData\ssh\administrators_authorized_keys'
    $dir = Split-Path -Parent $path
    if ($script:DryRun) {
        Set-Gate 'Public key installed' $true 'DryRun'
        Set-Gate 'Public key count exactly 1' $true 'DryRun'
        Set-Gate 'authorized_keys permissions' $true 'DryRun'
        return
    }
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $existing = ''
    if (Test-Path -LiteralPath $path) {
        $existing = Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue
        if ($null -eq $existing) { $existing = '' }
    }
    $want = $OtaconSshPubKey.Trim()
    if ($want -notmatch '^(ssh-ed25519|ecdsa-sha2-|ssh-rsa)\s+\S+') {
        Set-Gate 'Public key installed' $false 'embedded public key invalid'
        return
    }
    $lines = @()
    if ($existing.Trim()) {
        $lines = @($existing -split "`r?`n" | ForEach-Object { $_.TrimEnd() } | Where-Object { $_ -ne '' })
    }
    $already = @($lines | Where-Object { $_.Trim() -eq $want }).Count
    if ($already -eq 0) {
        $lines += $want
    }
    # Deduplicate exact want line if somehow multi
    $newLines = New-Object System.Collections.Generic.List[string]
    $seenWant = $false
    foreach ($l in $lines) {
        if ($l.Trim() -eq $want) {
            if (-not $seenWant) { $newLines.Add($want) | Out-Null; $seenWant = $true }
            continue
        }
        $newLines.Add($l) | Out-Null
    }
    $content = (($newLines -join "`n") + "`n")
    # Write as UTF-8 no BOM preferred for OpenSSH
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($path, $content, $utf8)

    $final = Get-Content -LiteralPath $path -Raw
    $count = @(($final -split "`r?`n") | Where-Object { $_.Trim() -eq $want }).Count
    Set-Gate 'Public key installed' ($count -ge 1)
    Set-Gate 'Public key count exactly 1' ($count -eq 1) "count=$count"

    # ACL: SYSTEM + Administrators (SID) only
    $adminSid = New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-544'
    $adminNt = $adminSid.Translate([System.Security.Principal.NTAccount]).Value
    $acl = Get-Acl -LiteralPath $path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($r in @($acl.Access)) { [void]$acl.RemoveAccessRule($r) }
    $sys = New-Object System.Security.AccessControl.FileSystemAccessRule('SYSTEM', 'FullControl', 'Allow')
    $adm = New-Object System.Security.AccessControl.FileSystemAccessRule($adminNt, 'FullControl', 'Allow')
    $acl.AddAccessRule($sys)
    $acl.AddAccessRule($adm)
    Set-Acl -LiteralPath $path -AclObject $acl

    $acl2 = Get-Acl -LiteralPath $path
    $bad = @($acl2.Access | Where-Object {
            $_.FileSystemRights.ToString() -match 'Write|FullControl|Modify' -and
            $_.IdentityReference.Value -notmatch 'SYSTEM|Administrators|S-1-5-32-544'
        })
    Set-Gate 'authorized_keys permissions' ($bad.Count -eq 0) ("rules=" + $acl2.Access.Count)
}

function Ensure-SshdPubkeyConfig {
    $cfg = 'C:\ProgramData\ssh\sshd_config'
    if ($script:DryRun) {
        Set-Gate 'PubkeyAuthentication' $true 'DryRun'
        return
    }
    if (-not (Test-Path -LiteralPath $cfg)) {
        Set-Gate 'PubkeyAuthentication' $false 'sshd_config missing'
        return
    }
    $backup = "$cfg.otacon-bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item -LiteralPath $cfg -Destination $backup -Force
    $raw = Get-Content -LiteralPath $cfg -Raw
    $lines = New-Object System.Collections.Generic.List[string]
    $seen = $false
    foreach ($line in ($raw -split "`r?`n")) {
        if ($line -match '^\s*PubkeyAuthentication\s+') {
            if (-not $seen) { $lines.Add('PubkeyAuthentication yes') | Out-Null; $seen = $true }
            continue
        }
        $lines.Add($line) | Out-Null
    }
    if (-not $seen) { $lines.Add('PubkeyAuthentication yes') | Out-Null }
    $newText = ($lines -join "`n").TrimEnd() + "`n"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($cfg, $newText, $utf8)

    $sshd = Join-Path $env:WINDIR 'System32\OpenSSH\sshd.exe'
    $valid = $true
    if (Test-Path -LiteralPath $sshd) {
        $p = Start-Process -FilePath $sshd -ArgumentList @('-t') -Wait -PassThru -WindowStyle Hidden
        if ($p.ExitCode -ne 0) { $valid = $false }
    }
    if (-not $valid) {
        Copy-Item -LiteralPath $backup -Destination $cfg -Force
        Set-Gate 'PubkeyAuthentication' $false 'sshd -t failed; restored backup'
        return
    }
    Restart-Service sshd -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $ok = Select-String -Path $cfg -Pattern '^\s*PubkeyAuthentication\s+yes\s*$' -Quiet
    Set-Gate 'PubkeyAuthentication' ([bool]$ok)
}

function Ensure-TailscaleFirewall {
    $ruleName = 'OtaconsKeep-SSH-Tailscale'
    if ($script:DryRun) {
        Set-Gate 'Restricted firewall rule' $true 'DryRun'
        Set-Gate 'No broad OpenSSH firewall exposure' $true 'DryRun'
        return
    }
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName $ruleName -Name $ruleName `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 `
            -RemoteAddress '100.64.0.0/10' -Enabled True | Out-Null
    } else {
        Set-NetFirewallRule -DisplayName $ruleName -Enabled True -Action Allow -ErrorAction SilentlyContinue
        $filt = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule (Get-NetFirewallRule -DisplayName $ruleName)
        # Ensure remote address if possible
        try {
            Set-NetFirewallRule -DisplayName $ruleName
            Get-NetFirewallRule -DisplayName $ruleName | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress '100.64.0.0/10'
        } catch {
            Write-OtaconLog 'WARN' ("Could not refresh firewall remote address: " + $_.Exception.Message)
        }
    }
    $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    $addr = $null
    if ($rule) {
        $addr = (Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule).RemoteAddress
    }
    $restrictedOk = ($rule -and $rule.Enabled -eq 'True' -and ($addr -contains '100.64.0.0/10' -or $addr -eq '100.64.0.0/10'))
    Set-Gate 'Restricted firewall rule' $restrictedOk ("remote=$addr")

    if ($restrictedOk) {
        $broad = Get-NetFirewallRule -DisplayName 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
        if ($broad -and $broad.Enabled -eq 'True') {
            $bAddr = (Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $broad).RemoteAddress
            $isAny = (-not $bAddr) -or ($bAddr -contains 'Any') -or ($bAddr -eq 'Any')
            if ($isAny) {
                Disable-NetFirewallRule -DisplayName 'OpenSSH-Server-In-TCP'
                Write-OtaconLog 'INFO' 'Disabled broad OpenSSH-Server-In-TCP (Any) after restricted rule confirmed'
            }
        }
    }
    $broad2 = Get-NetFirewallRule -DisplayName 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
    $broadBad = $false
    if ($broad2 -and $broad2.Enabled -eq 'True') {
        $b2 = (Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $broad2).RemoteAddress
        $broadBad = (-not $b2) -or ($b2 -contains 'Any') -or ($b2 -eq 'Any')
    }
    Set-Gate 'No broad OpenSSH firewall exposure' (-not $broadBad)
}

function Test-Port22Listening {
    if ($script:DryRun) {
        Set-Gate 'Port 22 listening' $true 'DryRun'
        return
    }
    $listen = Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue
    Set-Gate 'Port 22 listening' ([bool]$listen)
}

function Write-DesktopInfo([bool]$Ready) {
    if ($script:DryRun) { return }
    $status = if ($Ready) { 'REMOTE ACCESS READY' } else { 'REMOTE ACCESS SETUP INCOMPLETE' }
    $preferred = "ssh ${OtaconSshUser}@${OtaconAlias}"
    $fallback = if ($script:TailscaleIp) { "ssh ${OtaconSshUser}@$($script:TailscaleIp)" } else { '(Tailscale IP unavailable)' }
    $body = @"
OtaconsKeep Remote Support
$status

Recipient: $OtaconRecipient
Remote machine: $OtaconAlias
Windows SSH user: $OtaconSshUser
Windows hostname: $env:COMPUTERNAME
Tailscale IP: $($script:TailscaleIp)

Preferred connection:
$preferred

Fallback:
$fallback

You do not need to do anything else.
"@
    try {
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [IO.File]::WriteAllText($script:InfoPath, $body, $utf8)
        Write-OtaconLog 'INFO' "Wrote $($script:InfoPath)"
    } catch {
        Write-OtaconLog 'WARN' ("Desktop info file failed: " + $_.Exception.Message)
    }
}

function Show-Final([bool]$Ready) {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host 'OTACONSKEEP REMOTE SUPPORT' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    if ($Ready) {
        Write-Host ''
        Write-Host 'REMOTE ACCESS READY' -ForegroundColor Green
        Write-Host ''
        Write-Host "Recipient:        $OtaconRecipient"
        Write-Host "Remote machine:   $OtaconAlias"
        Write-Host "Windows SSH user: $OtaconSshUser"
        Write-Host "Tailscale IP:     $($script:TailscaleIp)"
        Write-Host ''
        Write-Host "Preferred:  ssh ${OtaconSshUser}@${OtaconAlias}" -ForegroundColor Green
        if ($script:TailscaleIp) {
            Write-Host "Fallback:   ssh ${OtaconSshUser}@$($script:TailscaleIp)"
        }
        Write-Host ''
        Write-Host "$OtaconRecipient does not need to do anything else." -ForegroundColor Green
        Write-Host "Don't worry — Otacon's got your back." -ForegroundColor Cyan
    } else {
        Write-Host ''
        Write-Host 'REMOTE ACCESS SETUP INCOMPLETE' -ForegroundColor Red
        Write-Host ''
        Write-Host 'Failed gates:' -ForegroundColor Yellow
        foreach ($k in $script:Gates.Keys) {
            if (-not $script:Gates[$k]) { Write-Host "  [FAIL] $k" -ForegroundColor Red }
        }
        Write-Host ''
        Write-Host 'Leave this window open and tell Xof. Check the log at:'
        Write-Host "  $($script:LogPath)"
    }
    Write-Host '============================================================' -ForegroundColor Cyan
}

# -------------------- main --------------------
Show-Banner
Write-OtaconLog 'INFO' "Recipient=$OtaconRecipient Alias=$OtaconAlias User=$OtaconSshUser DryRun=$($script:DryRun)"
Write-OtaconLog 'INFO' ("Host={0} User={1} OS={2} Arch={3}" -f $env:COMPUTERNAME, $env:USERNAME, [Environment]::OSVersion.VersionString, $env:PROCESSOR_ARCHITECTURE)

if (-not (Test-IsAdmin)) {
    if ($script:DryRun) {
        Write-OtaconLog 'WARN' 'DryRun: not elevated (continuing)'
        Set-Gate 'Administrator' $true 'DryRun non-elevated'
    } else {
        Write-OtaconLog 'INFO' 'Relaunching elevated…'
        $self = $PSCommandPath
        if (-not $self) { $self = $MyInvocation.MyCommand.Path }
        try {
            Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $self) | Out-Null
        } catch {
            Set-Gate 'Administrator' $false 'UAC declined or relaunch failed'
            Show-Final $false
            exit 1
        }
        exit 0
    }
} else {
    Set-Gate 'Administrator' $true
}

Install-TailscaleIfNeeded
Ensure-TailscaleEnrollment
Install-OpenSshServer
Ensure-SshdService
Install-OwnerPublicKey
Ensure-SshdPubkeyConfig
Ensure-TailscaleFirewall
Test-Port22Listening

$critical = @(
    'Administrator',
    'Tailscale installed',
    'Tailscale backend',
    'Tailscale authenticated',
    'Tailscale hostname',
    'Tailscale IPv4',
    'OpenSSH installed',
    'sshd exists',
    'sshd Running',
    'sshd Automatic',
    'Public key installed',
    'Public key count exactly 1',
    'authorized_keys permissions',
    'PubkeyAuthentication',
    'Port 22 listening',
    'Restricted firewall rule',
    'No broad OpenSSH firewall exposure'
)
$ready = $true
foreach ($g in $critical) {
    if (-not $script:Gates.Contains($g) -or -not $script:Gates[$g]) { $ready = $false }
}
# Unattended is soft-required — still track
if (-not $script:Gates.Contains('Tailscale unattended') -or -not $script:Gates['Tailscale unattended']) {
    Write-OtaconLog 'WARN' 'Tailscale unattended gate not confirmed'
}

Write-DesktopInfo $ready
Show-Final $ready
if ($ready) { exit 0 } else { exit 2 }
