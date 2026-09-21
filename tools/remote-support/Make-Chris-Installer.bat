@echo off
setlocal EnableExtensions
title OtaconsKeep - Make Chris installer
echo.
echo  OtaconsKeep: making Chris's installer...
echo  Downloading latest script from GitHub, then starting...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $p = Join-Path $env:TEMP 'Otacon-Make-Chris.ps1'; Write-Host ('Saving to ' + $p); Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/tools/remote-support/Make-Chris.ps1' -OutFile $p; if (-not (Test-Path $p)) { throw 'Download failed' }; Write-Host 'Download OK. Starting...'; & $p; exit $LASTEXITCODE } catch { Write-Host ''; Write-Host 'FAILED:' -ForegroundColor Red; Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
set EC=%ERRORLEVEL%
echo.
if not "%EC%"=="0" (
  echo  FAILED. Copy the red error text above and send it to Xof.
) else (
  echo  OK. Send Desktop\SEND-TO-CHRIS.bat to Chris.
)
echo.
pause
exit /b %EC%
