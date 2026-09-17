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
      Returns hashtable: Ok, ExitCode, Output, Stage, WindowsPath, LinuxPath
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Distro,
        [Parameter(Mandatory = $true)][string]$ScriptBody,
        [string]$User = "root",
        [string]$Label = "otacon-wsl"
    )
    $result = @{
        Ok          = $false
        ExitCode    = 1
        Output      = ""
        Stage       = "init"
        WindowsPath = ""
        LinuxPath   = ""
    }
    $winTmp = Join-Path $env:TEMP ("$Label-" + [guid]::NewGuid().ToString("n") + ".sh")
    $result.WindowsPath = $winTmp
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        $lf = [string]$ScriptBody
        $lf = $lf -replace "`r`n", "`n" -replace "`r", "`n"
        if (-not $lf.EndsWith("`n")) { $lf = $lf + "`n" }
        # Refuse UTF-8 BOM in the payload file (bash can choke on BOM as syntax).
        [System.IO.File]::WriteAllText($winTmp, $lf, $utf8NoBom)

        $linuxPath = ConvertTo-OtaconLinuxPath -Distro $Distro -WindowsPath $winTmp -User $User
        $result.LinuxPath = $linuxPath

        $result.Stage = "bash -n"
        $syntaxOut = & wsl.exe -d $Distro -u $User --exec bash -n $linuxPath 2>&1
        $syntaxCode = $LASTEXITCODE
        if ($null -eq $syntaxCode) { $syntaxCode = 1 }
        $result.ExitCode = [int]$syntaxCode
        $result.Output = ($syntaxOut | Out-String)
        if ([int]$syntaxCode -ne 0) {
            $result.Ok = $false
            return $result
        }

        $result.Stage = "bash"
        $runOut = & wsl.exe -d $Distro -u $User --exec bash $linuxPath 2>&1
        $runCode = $LASTEXITCODE
        if ($null -eq $runCode) { $runCode = 1 }
        $result.ExitCode = [int]$runCode
        $result.Output = ($runOut | Out-String)
        $result.Ok = ([int]$runCode -eq 0)
        return $result
    } catch {
        $result.Stage = "exception"
        $result.Ok = $false
        $result.ExitCode = 1
        $result.Output = $_.Exception.Message
        return $result
    } finally {
        Remove-Item -LiteralPath $winTmp -Force -ErrorAction SilentlyContinue
    }
}
