@echo off
REM ============================================================
REM  get-fix-codec.cmd
REM  Double-click this file. Do NOT paste it into CMD.
REM  Downloads OtaconsKeep-Setup.bat and runs --update --fix-codec.
REM  Avoids powershell -Command quoting (breaks when chat soft-quotes).
REM ============================================================
setlocal EnableExtensions
title Otacon Fix Codec
cd /d "%TEMP%"

del /f /q otacon-get.ps1 2>nul

REM Build URL in pieces so interactive paste never sees a lone "https:" token.
set "U1=http"
set "U1=%U1%s://raw.githubusercontent.com"
set "U2=/Otaconskeep/otacons-ai-ecosystem/main/OtaconsKeep-Setup.bat"

>otacon-get.ps1 echo try {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12} catch {}
>>otacon-get.ps1 echo $ProgressPreference = 'SilentlyContinue'
>>otacon-get.ps1 echo $out = Join-Path $env:TEMP 'OtaconsKeep-Setup.bat'
>>otacon-get.ps1 echo $url = '%U1%%U2%'
>>otacon-get.ps1 echo Write-Host "Downloading $url"
>>otacon-get.ps1 echo Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out
>>otacon-get.ps1 echo if (-not (Test-Path -LiteralPath $out)) { throw 'download failed' }
>>otacon-get.ps1 echo if ((Get-Item -LiteralPath $out).Length -lt 100) { throw 'download too small' }
>>otacon-get.ps1 echo Write-Host "Running Setup --update --fix-codec"
>>otacon-get.ps1 echo $p = Start-Process -FilePath $out -ArgumentList '--update','--fix-codec' -Wait -PassThru
>>otacon-get.ps1 echo exit $p.ExitCode

echo.
echo  Downloading OtaconsKeep Setup...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\otacon-get.ps1"
set "RC=%ERRORLEVEL%"
echo.
echo  Done. exit=%RC%
echo  Press any key to close.
pause >nul
exit /b %RC%
