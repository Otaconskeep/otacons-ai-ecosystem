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
$wakeSrc = Join-Path $scriptRoot "wake-otacon.ps1"
$KeepAliveScript = Join-Path $InstallerRoot "keep-ubuntu-awake.ps1"
Copy-Item -Path $wakeSrc -Destination $KeepAliveScript -Force

# Also keep a legacy copy name for older Open helpers.
Copy-Item -Path $wakeSrc -Destination (Join-Path $InstallerRoot "wake-otacon.ps1") -Force

$StartupDir = [Environment]::GetFolderPath("Startup")
if (-not $StartupDir) {
    throw "Could not resolve Windows Startup folder via [Environment]::GetFolderPath('Startup')"
}
$StartupLauncher = Join-Path $StartupDir "OtaconsKeep-KeepAlive.vbs"

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$KeepAliveScript`" -DistroName `"$DistroName`" -Port $Port"
$vbsLine = "CreateObject(""WScript.Shell"").Run ""powershell.exe $($psArgs.Replace('"','""'))"", 0, False"
Set-Content -Path $StartupLauncher -Value $vbsLine -Encoding ASCII

# Scheduled task remains as a belt-and-suspenders logon wake (same dynamic paths).
$vbsTaskPath = Join-Path $InstallerRoot "OtaconsKeep-KeepAlive.vbs"
Set-Content -Path $vbsTaskPath -Value $vbsLine -Encoding ASCII

$taskName = "OtaconAutoStart"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbsTaskPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Wakes the Otacon WSL environment at logon so Otacon is ready at http://localhost:$Port" | Out-Null

Write-Output "OK"
Write-Output "KeepAliveScript=$KeepAliveScript"
Write-Output "StartupLauncher=$StartupLauncher"
