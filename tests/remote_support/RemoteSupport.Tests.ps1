# Pester tests for OtaconsKeep remote-support helpers.
# Run: pwsh -NoProfile -File tests/remote_support/RemoteSupport.Tests.ps1

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. (Join-Path $root 'tools\remote-support\RemoteSupport.Common.ps1')

$hasPester = [bool](Get-Command Describe -ErrorAction SilentlyContinue)
if (-not $hasPester) {
    $failed = 0
    if (-not (Test-OtaconSshPublicKeyLine -Line 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal x')) { $failed++ }
    if (Test-OtaconSshPublicKeyLine -Line '-----BEGIN OPENSSH PRIVATE KEY-----') { $failed++ }
    $s = Protect-OtaconSecretText -Text 'tskey-auth-SUPERSECRETVALUE999' -Secrets @('tskey-auth-SUPERSECRETVALUE999')
    if ($s -ne '<REDACTED>') { $failed++ }
    $k = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal x'
    $a = Add-OtaconAuthorizedKeyLine -ExistingContent '' -PublicKeyLine $k
    $b = Add-OtaconAuthorizedKeyLine -ExistingContent $a.Content -PublicKeyLine $k
    if ($b.Added -or $b.Count -ne 1) { $failed++ }
    $bat = New-OtaconRemoteBatWrapper -EmbeddedPs1 "Write-Host 'hi'" -Recipient 'Josh'
    if ($bat -notmatch '___OTACON_PAYLOAD_B64_BEGIN___') { $failed++ }
    if (Test-OtaconPrivateKeyLeak -Text $bat) { $failed++ }
    if ($failed -gt 0) {
        Write-Host "Fallback checks FAIL count=$failed" -ForegroundColor Red
        exit 1
    }
    Write-Host 'Fallback checks PASS (Pester not installed)' -ForegroundColor Green
    exit 0
}

Describe 'RemoteSupport.Common' {
    It 'validates ssh public keys' {
        (Test-OtaconSshPublicKeyLine -Line 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal x') | Should -BeTrue
        (Test-OtaconSshPublicKeyLine -Line '-----BEGIN OPENSSH PRIVATE KEY-----') | Should -BeFalse
    }

    It 'redacts Tailscale auth keys' {
        $s = Protect-OtaconSecretText -Text 'tskey-auth-SUPERSECRETVALUE999' -Secrets @('tskey-auth-SUPERSECRETVALUE999')
        $s | Should -Be '<REDACTED>'
    }

    It 'does not duplicate authorized_keys lines' {
        $k = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal x'
        $a = Add-OtaconAuthorizedKeyLine -ExistingContent '' -PublicKeyLine $k
        $b = Add-OtaconAuthorizedKeyLine -ExistingContent $a.Content -PublicKeyLine $k
        $a.Added | Should -BeTrue
        $b.Added | Should -BeFalse
        $b.Count | Should -Be 1
    }

    It 'merges sshd_config without duplicating directives' {
        $c1 = Merge-OtaconSshdConfigLine -ConfigText "Port 22`n" -Directive 'PasswordAuthentication' -Value 'no'
        $c2 = Merge-OtaconSshdConfigLine -ConfigText $c1 -Directive 'PasswordAuthentication' -Value 'no'
        ([regex]::Matches($c2, 'PasswordAuthentication')).Count | Should -Be 1
    }

    It 'detects private key leaks' {
        (Test-OtaconPrivateKeyLeak -Text "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal x") | Should -BeFalse
        (Test-OtaconPrivateKeyLeak -Text "-----BEGIN OPENSSH PRIVATE KEY-----`nabc") | Should -BeTrue
    }

    It 'builds a BAT wrapper with payload markers' {
        $ps1 = "Write-Host 'hi'"
        $bat = New-OtaconRemoteBatWrapper -EmbeddedPs1 $ps1 -Recipient 'Josh'
        $bat | Should -Match '___OTACON_PAYLOAD_B64_BEGIN___'
        $bat | Should -Match 'Run as administrator'
        $bat | Should -Not -Match 'BEGIN OPENSSH PRIVATE KEY'
    }
}
