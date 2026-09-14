@echo off
REM ============================================================
REM  OtaconsKeep-Setup.bat  (public download name)
REM  Lone Downloads\ entry — fetches guided installer into
REM  %LOCALAPPDATA%\OtaconsKeep\installer then runs it.
REM  NEVER exits silently on fetch/download failure.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

set "BRANCH=main"
set "REPO_WEB=https://github.com/Otaconskeep/otacons-ai-ecosystem"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "KEEP=%LOCALAPPDATA%\OtaconsKeep"
set "INST=%KEEP%\installer"
set "LOGDIR=%KEEP%\Logs"
set "LOGFILE=%LOGDIR%\installer.log"
set "ASSISTANT=%INST%\deploy\windows-setup-assistant.ps1"
set "FETCH_PS1=%INST%\deploy\bootstrap-fetch.ps1"
set "DEBUG="
set "ARGS="

REM --- parse args (pass through; enable --debug) ---
:PARSE_ARGS
if "%~1"=="" goto ARGS_DONE
if /I "%~1"=="--debug" (
  set "DEBUG=1"
  shift
  goto PARSE_ARGS
)
if /I "%~1"=="-debug" (
  set "DEBUG=1"
  shift
  goto PARSE_ARGS
)
set "ARGS=!ARGS! %~1"
shift
goto PARSE_ARGS
:ARGS_DONE

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
if not exist "%INST%\deploy" mkdir "%INST%\deploy" >nul 2>&1

call :LOG "==== OtaconsKeep-Setup.bat start DEBUG=%DEBUG% ===="
call :LOG "INST=%INST%"
call :LOG "USERPROFILE=%USERPROFILE%"

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

if defined DEBUG (
  echo [DEBUG] LOGFILE=%LOGFILE%
  echo [DEBUG] INST=%INST%
  echo [DEBUG] RAW=%RAW%
)

REM If this copy already sits next to deploy\windows-setup-assistant.ps1
REM (zip / git clone / LocalAppData tree), run that tree — do not re-fetch.
set "LOCAL_ASSISTANT=%~dp0deploy\windows-setup-assistant.ps1"
if exist "%LOCAL_ASSISTANT%" (
  call :LOG "local tree detected; skipping bootstrap fetch"
  call "%~dp0install_otacon.bat" %ARGS%
  set "RC=!ERRORLEVEL!"
  call :LOG "install_otacon.bat exit=!RC!"
  if not "!RC!"=="0" call :STAY_OPEN_AFTER_CHILD !RC!
  exit /b !RC!
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
echo  Log file:
echo    %LOGFILE%
echo.

:FETCH_RETRY
call :LOG "FETCH_RETRY begin"
call :ENSURE_FETCH_HELPER
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" (
  call :SHOW_DOWNLOAD_FAILED !RC! "preparing the download helper"
  if /I "!CHOICE!"=="R" goto FETCH_RETRY
  exit /b 1
)

echo.
echo  [1/2] downloading otaconskeep
echo  source
echo    %REPO_WEB%
echo  status
echo    downloading...
echo  Do not close this window.
echo.

if defined DEBUG echo [DEBUG] powershell -File "%FETCH_PS1%" -DestRoot "%INST%" ...
REM Visible on console; bootstrap-fetch.ps1 also appends to installer.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -DestRoot "%INST%" -RawBase "%RAW%" -LogFile "%LOGFILE%" -Manifest full %DEBUG_SWITCH%
set "RC=!ERRORLEVEL!"
call :LOG "bootstrap-fetch.ps1 exit=!RC!"

if not "!RC!"=="0" (
  call :SHOW_DOWNLOAD_FAILED !RC! "downloading otaconskeep from github"
  if /I "!CHOICE!"=="R" goto FETCH_RETRY
  exit /b 1
)

if not exist "%ASSISTANT%" (
  call :LOG "ASSISTANT missing after fetch: %ASSISTANT%"
  call :SHOW_DOWNLOAD_FAILED 2 "verifying downloaded setup files"
  if /I "!CHOICE!"=="R" goto FETCH_RETRY
  exit /b 1
)

echo.
echo  status
echo    verifying files... OK
echo.
call :LOG "fetch OK; launching install_otacon.bat"

REM Re-enter via the repo entry point inside LocalAppData
if defined DEBUG set "ARGS=!ARGS! --debug"
call "%INST%\install_otacon.bat" %ARGS%
set "RC=!ERRORLEVEL!"
call :LOG "install_otacon.bat exit=!RC!"
if not "!RC!"=="0" call :STAY_OPEN_AFTER_CHILD !RC!
exit /b !RC!

REM ============================================================
REM  Subroutines
REM ============================================================

:LOG
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] %~1
exit /b 0

:STAY_OPEN_AFTER_CHILD
REM Child (PowerShell guided UI) should already have paused; still keep
REM this console alive if it returned failure without waiting.
set "CHILD_RC=%~1"
echo.
echo ============================================================
echo  SETUP WINDOW STAYING OPEN
echo ============================================================
echo  The setup helper finished with exit code %CHILD_RC%.
echo  If you already used R / O / X in the helper, press a key to close.
echo  Log: %LOGFILE%
echo ============================================================
if defined DEBUG (
  echo [DEBUG] child exit=%CHILD_RC%
  echo [DEBUG] press a key — debug mode never auto-closes on failure
)
pause >nul
exit /b 0

:SHOW_DOWNLOAD_FAILED
set "FAIL_RC=%~1"
set "FAIL_STEP=%~2"
set "CHOICE="
call :LOG "SHOW_DOWNLOAD_FAILED rc=%FAIL_RC% step=%FAIL_STEP%"
echo.
echo ============================================================
echo               DOWNLOAD FAILED
echo ============================================================
echo.
echo  otacon could not download the required files
echo.
echo  nothing has been damaged
echo.
echo  failed step
echo  %FAIL_STEP%
echo.
echo  exit code
echo  %FAIL_RC%
echo.
echo  possible causes
echo  internet connection
echo  github temporarily unavailable
echo  security software blocked the download
echo  powershell or curl blocked by policy
echo.
echo  technical details
echo  %LOGFILE%
echo.
echo  [R] retry
echo  [L] open logs
echo  [X] exit
echo.
echo ============================================================
echo.
:DF_CHOICE
set /p "CHOICE=  Choice [R/L/X]: "
if /I "!CHOICE!"=="L" (
  start "" explorer.exe "%LOGDIR%"
  goto DF_CHOICE
)
if /I "!CHOICE!"=="R" (
  call :LOG "user chose RETRY"
  exit /b 0
)
if /I "!CHOICE!"=="X" (
  call :LOG "user chose EXIT"
  exit /b 0
)
goto DF_CHOICE

:ENSURE_FETCH_HELPER
REM Obtain bootstrap-fetch.ps1 without depending on a prior fetch.
if exist "%FETCH_PS1%" (
  for %%A in ("%FETCH_PS1%") do if %%~zA GEQ 40 (
    call :LOG "bootstrap-fetch.ps1 already present"
    exit /b 0
  )
)

echo.
echo  [0/2] preparing download helper
echo  source
echo    %RAW%/deploy/bootstrap-fetch.ps1
echo  status
echo    connecting...
echo.

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

REM Prefer curl.exe (Windows 10/11) — capture exit code, never silent.
where curl.exe >nul 2>&1
if not errorlevel 1 (
  call :LOG "using curl.exe to fetch bootstrap-fetch.ps1"
  if defined DEBUG echo [DEBUG] curl.exe -fsSL ... -o "%FETCH_PS1%"
  echo  status
  echo    downloading...
  curl.exe -fsSL --connect-timeout 20 --max-time 120 -o "%FETCH_PS1%" "%RAW%/deploy/bootstrap-fetch.ps1" >>"%LOGFILE%" 2>&1
  set "RC=!ERRORLEVEL!"
  call :LOG "curl bootstrap-fetch exit=!RC!"
  if "!RC!"=="0" if exist "%FETCH_PS1%" (
    for %%A in ("%FETCH_PS1%") do if %%~zA GEQ 40 (
      echo  status
      echo    verifying files... OK
      exit /b 0
    )
  )
  call :LOG "curl helper fetch insufficient; trying PowerShell"
)

echo  status
echo    downloading via PowerShell...
if defined DEBUG echo [DEBUG] Invoke-WebRequest bootstrap-fetch.ps1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$log='%LOGFILE%'; $out='%FETCH_PS1%'; $url='%RAW%/deploy/bootstrap-fetch.ps1';" ^
  "function L($m){ Add-Content -Path $log -Value ('['+(Get-Date -Format o)+'] [FETCH] '+$m) -Encoding UTF8 };" ^
  "try {" ^
  "  L ('GET '+$url);" ^
  "  New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null;" ^
  "  Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 120;" ^
  "  if(-not (Test-Path $out) -or ((Get-Item $out).Length -lt 40)){ throw 'helper file missing or too small' };" ^
  "  L ('OK bytes='+(Get-Item $out).Length);" ^
  "  exit 0" ^
  "} catch {" ^
  "  L ('ERROR '+$_.Exception.Message);" ^
  "  Write-Host $_.Exception.Message;" ^
  "  exit 1" ^
  "}"
set "RC=!ERRORLEVEL!"
call :LOG "powershell helper fetch exit=!RC!"
if not "!RC!"=="0" exit /b !RC!
if not exist "%FETCH_PS1%" exit /b 2
for %%A in ("%FETCH_PS1%") do if %%~zA LSS 40 exit /b 2
echo  status
echo    verifying files... OK
exit /b 0
