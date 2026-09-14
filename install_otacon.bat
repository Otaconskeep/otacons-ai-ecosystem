@echo off
REM ============================================================
REM  OtaconsKeep Windows Setup — entry point
REM  Double-click this file. Do not close the window unless asked.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

set "SCRIPT_DIR=%~dp0"
set "KEEP_DIR=%LOCALAPPDATA%\OtaconsKeep"
set "LOG_DIR=%KEEP_DIR%\Logs"
set "ASSISTANT=%SCRIPT_DIR%deploy\windows-setup-assistant.ps1"
set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

REM --- argument modes ---
set "MODE="
if /I "%~1"=="--status" set "MODE=-Status"
if /I "%~1"=="-status" set "MODE=-Status"
if /I "%~1"=="--diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="-diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="--open" set "MODE=-Open"
if /I "%~1"=="-open" set "MODE=-Open"
if /I "%~1"=="--resume" set "MODE=-Resume"
if /I "%~1"=="-resume" set "MODE=-Resume"

call :ENSURE_ASSISTANT
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  SETUP NEEDS HELP
  echo ============================================================
  echo Could not download the OtaconsKeep setup assistant.
  echo Check your internet connection, then try again.
  echo.
  echo Log folder:
  echo   %LOG_DIR%
  echo.
  echo This window will stay open. Press a letter key to exit.
  echo ============================================================
  pause >nul
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ASSISTANT%" %MODE% -RepoRoot "%SCRIPT_DIR:~0,-1%" -Branch "%BRANCH%"
set "RC=%ERRORLEVEL%"
exit /b %RC%

REM ------------------------------------------------------------
:ENSURE_ASSISTANT
if exist "%ASSISTANT%" exit /b 0

echo.
echo ============================================================
echo  OTACONSKEEP SETUP
echo ============================================================
echo Downloading setup files ^(first run only^)...
echo Do not close this window.
echo ============================================================
echo.

if not exist "%SCRIPT_DIR%deploy" mkdir "%SCRIPT_DIR%deploy" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='%RAW%'; $dest='%SCRIPT_DIR%deploy';" ^
  "New-Item -ItemType Directory -Force -Path $dest | Out-Null;" ^
  "$files=@('windows-setup-assistant.ps1','find-ubuntu.ps1','install-wake-task.ps1','wake-otacon.ps1');" ^
  "foreach($f in $files){" ^
  "  $url=\"$base/deploy/$f\";" ^
  "  $out=Join-Path $dest $f;" ^
  "  Write-Host ('  fetching '+$f);" ^
  "  Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing;" ^
  "  if(-not (Test-Path $out) -or ((Get-Item $out).Length -lt 20)){ throw \"missing $f\" }" ^
  "}"

if not exist "%ASSISTANT%" exit /b 1
exit /b 0
