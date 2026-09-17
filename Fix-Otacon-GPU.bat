@echo off
REM ============================================================
REM  Fix-Otacon-GPU.bat
REM  Double-click only. Fixes false "no GPU detected" on WSL.
REM  Pulls latest code, turns GPU detection back on, restarts Codec.
REM ============================================================
setlocal EnableExtensions
title Otacon Fix GPU
cd /d "%TEMP%"

del /f /q otacon-fix-gpu.ps1 2>nul

set "U1=http"
set "U1=%U1%s://raw.githubusercontent.com"
set "U2=/Otaconskeep/otacons-ai-ecosystem/main/deploy/fix-otacon-gpu.ps1"

>otacon-fix-gpu.ps1 echo try {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12} catch {}
>>otacon-fix-gpu.ps1 echo $ProgressPreference = 'SilentlyContinue'
>>otacon-fix-gpu.ps1 echo $out = Join-Path $env:TEMP 'fix-otacon-gpu.ps1'
>>otacon-fix-gpu.ps1 echo $url = '%U1%%U2%'
>>otacon-fix-gpu.ps1 echo Write-Host " Downloading GPU fix..."
>>otacon-fix-gpu.ps1 echo Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out
>>otacon-fix-gpu.ps1 echo if (-not (Test-Path -LiteralPath $out)) { throw 'download failed' }
>>otacon-fix-gpu.ps1 echo Write-Host " Running GPU fix (leave this window open)..."
>>otacon-fix-gpu.ps1 echo ^& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $out
>>otacon-fix-gpu.ps1 echo exit $LASTEXITCODE

echo.
echo  ============================================================
echo   OTACON GPU FIX
echo  ============================================================
echo.
echo   Fixes false "no GPU detected". One step.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\otacon-fix-gpu.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo   Done. Hard-refresh Codec with Ctrl+Shift+R.
) else (
  echo   Fix failed. exit=%RC%
)
echo.
echo  Press any key to close.
pause >nul
exit /b %RC%
