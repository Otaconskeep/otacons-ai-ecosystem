# Registers (or re-registers) Otacon keepalive so WSL stays warm at logon.
# Paths are always derived from the invoking Windows profile - never hardcoded.
param(
    [Parameter(Mandatory = $true)][string]$DistroName,
    [int]$Port = 5757
)

$ErrorActionPreference = "Stop"

$InstallerRoot = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
New-Item -ItemType Directory -Force -Path $InstallerRoot | Out-Null

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$keepSrc = Join-Path $scriptRoot "keep-ubuntu-awake.ps1"
$wakeSrc = Join-Path $scriptRoot "wake-otacon.ps1"
if (-not (Test-Path -LiteralPath $keepSrc)) {
    throw "missing deploy/keep-ubuntu-awake.ps1"
}

$KeepAliveScript = Join-Path $InstallerRoot "keep-ubuntu-awake.ps1"
Copy-Item -Path $keepSrc -Destination $KeepAliveScript -Force
if (Test-Path -LiteralPath $wakeSrc) {
    Copy-Item -Path $wakeSrc -Destination (Join-Path $InstallerRoot "wake-otacon.ps1") -Force
}

$StartupDir = [Environment]::GetFolderPath("Startup")
if (-not $StartupDir) {
    throw "Could not resolve Windows Startup folder via [Environment]::GetFolderPath('Startup')"
}
$StartupLauncher = Join-Path $StartupDir "OtaconsKeep-KeepAlive.vbs"

# Long-lived keepalive at sign-in (hidden). Distro is the selected install distro.
$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$KeepAliveScript`" -DistroName `"$DistroName`" -Port $Port"
$vbsLine = "CreateObject(""WScript.Shell"").Run ""powershell.exe $($psArgs.Replace('"','""'))"", 0, False"
Set-Content -Path $StartupLauncher -Value $vbsLine -Encoding ASCII

$vbsTaskPath = Join-Path $InstallerRoot "OtaconsKeep-KeepAlive.vbs"
Set-Content -Path $vbsTaskPath -Value $vbsLine -Encoding ASCII

# One-shot wake task (bounded) as belt-and-suspenders beside long-lived Startup keepalive.
$wakeDst = Join-Path $InstallerRoot "wake-otacon.ps1"
$taskName = "OtaconAutoStart"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $wakeDst) {
    $wakeVbs = Join-Path $InstallerRoot "OtaconsKeep-WakeOnce.vbs"
    $wakePs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wakeDst`" -DistroName `"$DistroName`" -Port $Port"
    $wakeLine = "CreateObject(""WScript.Shell"").Run ""powershell.exe $($wakePs.Replace('"','""'))"", 0, False"
    Set-Content -Path $wakeVbs -Value $wakeLine -Encoding ASCII
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$wakeVbs`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "One-shot Otacon wake at logon (keepalive is Startup OtaconsKeep-KeepAlive.vbs)" | Out-Null
}

Write-Output "OK"
Write-Output "KeepAliveScript=$KeepAliveScript"
Write-Output "StartupLauncher=$StartupLauncher"
Write-Output "DistroName=$DistroName"
