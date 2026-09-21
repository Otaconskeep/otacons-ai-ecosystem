# OtaconsKeep — one-file owner installer for Chris.
# Designed & Engineered by Antonio G. Garcia // Otaconskeep

[CmdletBinding()]
param()

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Prefer local Make-Josh.ps1 sibling logic by re-downloading parameterized script body.
# Simplest: dot-source Make-Josh.ps1 with different defaults via invoke.
$josh = Join-Path $here 'Make-Josh.ps1'
if (-not (Test-Path -LiteralPath $josh)) {
    $josh = Join-Path $env:TEMP 'Otacon-Make-Josh.ps1'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/tools/remote-support/Make-Josh.ps1' -OutFile $josh
}

& $josh -Recipient 'Chris' -Alias 'otacon-chris' -SshUser 'Chris'
exit $LASTEXITCODE
