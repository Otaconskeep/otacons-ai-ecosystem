@echo off
REM ============================================================
REM  OtaconsKeep-Setup.bat  (public download name)
REM  Safe for a lone Downloads\ file — fetches the guided installer
REM  into %%LOCALAPPDATA%%\OtaconsKeep\installer then runs it.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "KEEP=%LOCALAPPDATA%\OtaconsKeep"
set "INST=%KEEP%\installer"
set "LOG=%KEEP%\Logs"
set "ASSISTANT=%INST%\deploy\windows-setup-assistant.ps1"

if not exist "%LOG%" mkdir "%LOG%" >nul 2>&1
if not exist "%INST%\deploy" mkdir "%INST%\deploy" >nul 2>&1

REM If this copy already sits next to deploy\windows-setup-assistant.ps1
REM (zip / git clone), run that tree instead of re-downloading.
set "LOCAL_ASSISTANT=%~dp0deploy\windows-setup-assistant.ps1"
if exist "%LOCAL_ASSISTANT%" (
  call "%~dp0install_otacon.bat" %*
  exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo                  OTACONSKEEP SETUP
echo ============================================================
echo.
echo                  O T A C O N
echo.
echo           WINDOWS INSTALLATION ASSISTANT
echo.
echo ============================================================
echo.
echo  Preparing setup files on this computer...
echo  Do not close this window.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$base='%RAW%'; $inst='%INST%';" ^
  "New-Item -ItemType Directory -Force -Path (Join-Path $inst 'deploy') | Out-Null;" ^
  "$map=@{ " ^
  "  'install_otacon.bat'='install_otacon.bat';" ^
  "  'OtaconsKeep-Setup.bat'='OtaconsKeep-Setup.bat';" ^
  "  'deploy/windows-setup-assistant.ps1'='deploy/windows-setup-assistant.ps1';" ^
  "  'deploy/find-ubuntu.ps1'='deploy/find-ubuntu.ps1';" ^
  "  'deploy/install-wake-task.ps1'='deploy/install-wake-task.ps1';" ^
  "  'deploy/wake-otacon.ps1'='deploy/wake-otacon.ps1'" ^
  "};" ^
  "foreach($k in $map.Keys){" ^
  "  $url=\"$base/$k\";" ^
  "  $out=Join-Path $inst $k;" ^
  "  New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null;" ^
  "  Write-Host ('  [ OTACON ] fetching '+$k);" ^
  "  Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing;" ^
  "  if(-not (Test-Path $out) -or ((Get-Item $out).Length -lt 40)){ throw \"Bad download: $k\" }" ^
  "}"

if not exist "%ASSISTANT%" (
  echo.
  echo ============================================================
  echo  SETUP NEEDS HELP
  echo ============================================================
  echo Could not download installer files from GitHub.
  echo Check your internet connection, then double-click this file again.
  echo.
  echo Having trouble downloading?
  echo Use the GitHub ZIP from the Otaconskeep website instead.
  echo.
  echo This window will stay open. Press a letter key to exit.
  echo ============================================================
  pause >nul
  exit /b 1
)

REM Re-enter via the repo entry point inside LocalAppData
call "%INST%\install_otacon.bat" %*
exit /b %ERRORLEVEL%
