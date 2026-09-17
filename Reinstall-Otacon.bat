@echo off
REM ============================================================
REM  Reinstall-Otacon.bat
REM  Double-click only. No flags. No PowerShell knowledge needed.
REM  Downloads a fresh Setup and runs a full reinstall/update.
REM ============================================================
setlocal EnableExtensions
title Otacon Reinstall
cd /d "%TEMP%"

del /f /q otacon-reinstall.ps1 2>nul

REM Build URL in pieces so chat soft-quotes never break https:
set "U1=http"
set "U1=%U1%s://raw.githubusercontent.com"
set "U2=/Otaconskeep/otacons-ai-ecosystem/main/OtaconsKeep-Setup.bat"

>otacon-reinstall.ps1 echo try {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12} catch {}
>>otacon-reinstall.ps1 echo $ProgressPreference = 'SilentlyContinue'
>>otacon-reinstall.ps1 echo $out = Join-Path $env:TEMP 'OtaconsKeep-Setup.bat'
>>otacon-reinstall.ps1 echo $url = '%U1%%U2%'
>>otacon-reinstall.ps1 echo Write-Host ""
>>otacon-reinstall.ps1 echo Write-Host " Downloading latest Otacon Setup..."
>>otacon-reinstall.ps1 echo Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out
>>otacon-reinstall.ps1 echo if (-not (Test-Path -LiteralPath $out)) { throw 'download failed' }
>>otacon-reinstall.ps1 echo if ((Get-Item -LiteralPath $out).Length -lt 100) { throw 'download too small' }
>>otacon-reinstall.ps1 echo Write-Host " Reinstalling Otacon (this can take a while). Leave this window open."
>>otacon-reinstall.ps1 echo Write-Host ""
>>otacon-reinstall.ps1 echo $p = Start-Process -FilePath $out -ArgumentList '--update','--reinstall' -Wait -PassThru
>>otacon-reinstall.ps1 echo exit $p.ExitCode

echo.
echo  ============================================================
echo   OTACON REINSTALL
echo  ============================================================
echo.
echo   One step. Leave this window open until it finishes.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\otacon-reinstall.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo   Done. Open Codec and hard-refresh the page ^(Ctrl+Shift+R^).
) else (
  echo   Something went wrong. exit=%RC%
  echo   You can try again, or ask whoever sent you this file for help.
)
echo.
echo  Press any key to close.
pause >nul
exit /b %RC%
