@echo off
REM ============================================================
REM  OtaconExpansion-Setup.bat
REM  Real Expansion installer: detects Core Keep, installs
REM  foundation roster via WSL, verifies Expansion health.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title Otacon Expansion Setup

set "OTACON_SETUP_SELF=%~f0"
set "ENC_PS1=%~dp0deploy\check-bat-encoding.ps1"
if exist "%ENC_PS1%" goto ENC_VIA_FILE
goto ENC_VIA_ENV
:ENC_VIA_FILE
powershell -NoProfile -ExecutionPolicy Bypass -File "%ENC_PS1%" -Path "%~f0"
goto ENC_AFTER_CHECK
:ENC_VIA_ENV
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $p = $env:OTACON_SETUP_SELF; if (-not (Test-Path -LiteralPath $p)) { Write-Host 'ERROR: installer file not found'; exit 2 }; $b = [IO.File]::ReadAllBytes($p); if ($b.Length -lt 8) { exit 2 }; if ($b[0] -eq 255 -and $b[1] -eq 254) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 254 -and $b[1] -eq 255) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191) { Write-Host 'ERROR: UTF-8 BOM is not allowed in .bat files. Re-download from the Otaconskeep website.'; exit 4 }; $bare = 0; for ($i = 0; $i -lt $b.Length; $i++) { if ($b[$i] -eq 10 -and ($i -eq 0 -or $b[$i-1] -ne 13)) { $bare++ } }; if ($bare -gt 0) { Write-Host 'ERROR: Unix line endings. Re-download OtaconExpansion-Setup.bat from the website.'; exit 5 }; exit 0 }"
:ENC_AFTER_CHECK
if errorlevel 1 goto ENC_FAIL
goto ENC_OK
:ENC_FAIL
echo.
echo  This installer file is damaged or was saved with the wrong encoding.
echo  Delete it, re-download from otaconskeep.com/premium/, and run again.
echo.
pause >nul
exit /b 1
:ENC_OK

set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "KEEP=%LOCALAPPDATA%\OtaconsKeep"
set "INST=%KEEP%\installer"
set "LOGDIR=%KEEP%\Logs"
set "LOGFILE=%LOGDIR%\expansion-installer.log"
set "FETCH_PS1=%INST%\deploy\bootstrap-fetch.ps1"
set "EXP_PS1=%INST%\deploy\install-otacon-expansion.ps1"
set "WSL_PS1=%INST%\deploy\wsl-bash-file.ps1"
set "DOWNLOAD_ONE=%INST%\deploy\download-one.ps1"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] Expansion Setup begin

REM Dev tree: run from repo checkout when helpers are beside this bat
if exist "%~dp0deploy\install-otacon-expansion.ps1" if exist "%~dp0deploy\wsl-bash-file.ps1" if exist "%~dp0install_otacon_expansion.sh" (
  echo.
  echo  [OTACON] Dev tree detected - running Expansion installer from this folder.
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\install-otacon-expansion.ps1" -RepoRoot "%~dp0" -OpenBrowser
  set "RC=!ERRORLEVEL!"
  goto DONE
)

echo.
echo  ============================================================
echo    OTACON EXPANSION SETUP
echo  ============================================================
echo.
echo  Preparing installer helpers...

if not exist "%INST%\deploy" mkdir "%INST%\deploy" >nul 2>&1

REM Always refresh bootstrap-fetch first (same pattern as Core Setup)
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}; $ProgressPreference='SilentlyContinue'; $out=Join-Path $env:LOCALAPPDATA 'OtaconsKeep\installer\deploy\bootstrap-fetch.ps1'; New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null; Invoke-WebRequest -UseBasicParsing -Uri '%RAW%/deploy/bootstrap-fetch.ps1' -OutFile $out; if (-not (Test-Path -LiteralPath $out)) { exit 1 }; exit 0"
if errorlevel 1 (
  echo  Failed to download bootstrap-fetch.ps1
  pause >nul
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -Manifest full -Branch "%BRANCH%" -RawBase "%RAW%" -InstallRoot "%INST%"
if errorlevel 1 (
  echo  Failed to refresh installer bundle.
  pause >nul
  exit /b 1
)

REM Ensure Expansion-specific helpers (may already be in release.json)
if not exist "%EXP_PS1%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%RAW%/deploy/install-otacon-expansion.ps1' -OutFile '%EXP_PS1%'"
)
if not exist "%INST%\install_otacon_expansion.sh" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%RAW%/install_otacon_expansion.sh' -OutFile '%INST%\install_otacon_expansion.sh'"
)

if not exist "%EXP_PS1%" (
  echo  Expansion installer helper missing after fetch.
  pause >nul
  exit /b 1
)
if not exist "%WSL_PS1%" (
  echo  WSL transport helper missing after fetch.
  pause >nul
  exit /b 1
)

findstr /C:"Invoke-OtaconWslBashFile" "%EXP_PS1%" >nul
if errorlevel 1 (
  echo  Expansion installer helper looks incomplete. Re-download from the website.
  pause >nul
  exit /b 1
)

echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%EXP_PS1%" -RepoRoot "%INST%" -OpenBrowser
set "RC=!ERRORLEVEL!"

:DONE
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] Expansion Setup exit=!RC!
echo.
if "!RC!"=="0" (
  echo  Expansion install finished.
) else (
  echo  Expansion install failed. exit=!RC!
  echo  Log: %LOGFILE%
)
echo.
echo  Press any key to close.
pause >nul
exit /b !RC!
