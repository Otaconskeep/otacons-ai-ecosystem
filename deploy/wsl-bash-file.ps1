# Shared Windows -> WSL Bash transport.
# Rule: never pass nontrivial multiline Bash through bash -c / bash -lc.
# Write a temp .sh (UTF-8 no BOM, LF), bash -n, then bash <file>.

function ConvertTo-OtaconLinuxPath {
    param(
        [Parameter(Mandatory = $true)][string]$Distro,
        [Parameter(Mandatory = $true)][string]$WindowsPath,
        [string]$User = "root"
    )
    $full = [System.IO.Path]::GetFullPath($WindowsPath)
    $converted = (& wsl.exe -d $Distro -u $User --exec wslpath -a $full 2>$null | Out-String).Trim()
    if ($converted -and $converted.StartsWith("/")) { return $converted }
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = ($Matches[2] -replace '\\', '/')
        return "/mnt/$drive/$rest"
    }
    throw "Could not convert Windows path to WSL path: $full"
}

function Invoke-OtaconWslBashFile {
    <#
      Write $ScriptBody to a temp .sh and run it under WSL.
      Returns hashtable: Ok, ExitCode, Output, Stage, WindowsPath, LinuxPath, FailureClass
      FailureClass:
        none | transport | syntax | script
      - transport/syntax = installer machinery (path/BOM/bash -n)
      - script = Bash ran; nonzero exit is the *payload* (e.g. E2E exit 8), not transport
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Distro,
        [Parameter(Mandatory = $true)][string]$ScriptBody,
        [string]$User = "root",
        [string]$Label = "otacon-wsl"
    )
    $result = @{
        Ok            = $false
        ExitCode      = 1
        Output        = ""
        Stage         = "init"
        WindowsPath   = ""
        LinuxPath     = ""
        FailureClass  = "transport"
    }
    $winTmp = Join-Path $env:TEMP ("$Label-" + [guid]::NewGuid().ToString("n") + ".sh")
    $result.WindowsPath = $winTmp
    $linuxTmp = "/tmp/$Label-" + [guid]::NewGuid().ToString("n") + ".sh"
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        $lf = [string]$ScriptBody
        $lf = $lf -replace "`r`n", "`n" -replace "`r", "`n"
        if (-not $lf.EndsWith("`n")) { $lf = $lf + "`n" }
        # Refuse UTF-8 BOM in the payload file (bash can choke on BOM as syntax).
        [System.IO.File]::WriteAllText($winTmp, $lf, $utf8NoBom)

        # Prefer a native Linux /tmp path - /mnt/c temps can hit mount/permission quirks.
        $result.Stage = "stage-to-/tmp"
        $winLinux = $null
        try {
            $winLinux = ConvertTo-OtaconLinuxPath -Distro $Distro -WindowsPath $winTmp -User $User
        } catch {
            $result.Stage = "wslpath"
            $result.Ok = $false
            $result.ExitCode = 1
            $result.FailureClass = "transport"
            $result.Output = $_.Exception.Message
            return $result
        }
        $stageOut = & wsl.exe -d $Distro -u $User --exec bash -c "cp -f '$winLinux' '$linuxTmp' && chmod 0700 '$linuxTmp'" 2>&1
        $stageCode = $LASTEXITCODE
        if ($null -eq $stageCode) { $stageCode = 1 }
        if ([int]$stageCode -ne 0) {
            # Fall back to running directly from the Windows-mounted path.
            $linuxTmp = $winLinux
            $result.Output = ("stage-to-/tmp failed; falling back to mounted path: " + ($stageOut | Out-String))
        }
        $result.LinuxPath = $linuxTmp

        $result.Stage = "bash -n"
        $syntaxOut = & wsl.exe -d $Distro -u $User --exec bash -n $linuxTmp 2>&1
        $syntaxCode = $LASTEXITCODE
        if ($null -eq $syntaxCode) { $syntaxCode = 1 }
        $result.ExitCode = [int]$syntaxCode
        $result.Output = (($result.Output + "`n" + ($syntaxOut | Out-String)).Trim())
        if ([int]$syntaxCode -ne 0) {
            $result.Ok = $false
            $result.FailureClass = "syntax"
            return $result
        }

        $result.Stage = "bash"
        $runOut = & wsl.exe -d $Distro -u $User --exec bash $linuxTmp 2>&1
        $runCode = $LASTEXITCODE
        if ($null -eq $runCode) { $runCode = 1 }
        $result.ExitCode = [int]$runCode
        $result.Output = ($runOut | Out-String)
        $result.Ok = ([int]$runCode -eq 0)
        # Nonzero from the payload script is NOT a transport/syntax failure (Josh vs Cristo).
        $result.FailureClass = if ($result.Ok) { "none" } else { "script" }
        return $result
    } catch {
        $result.Stage = "exception"
        $result.Ok = $false
        $result.ExitCode = 1
        $result.FailureClass = "transport"
        $result.Output = $_.Exception.Message
        return $result
    } finally {
        Remove-Item -LiteralPath $winTmp -Force -ErrorAction SilentlyContinue
        try {
            & wsl.exe -d $Distro -u $User --exec rm -f $linuxTmp 2>$null | Out-Null
        } catch {}
    }
}
