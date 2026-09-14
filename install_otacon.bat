@echo off
REM ============================================================
REM  OtaconsKeep Windows Setup — entry point
REM  Double-click this file. Do not close the window unless asked.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM  NEVER exits silently after fetch or PowerShell failure.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

set "SCRIPT_DIR=%~dp0"
set "KEEP_DIR=%LOCALAPPDATA%\OtaconsKeep"
set "LOG_DIR=%KEEP_DIR%\Logs"
set "LOGFILE=%LOG_DIR%\installer.log"
set "ASSISTANT=%SCRIPT_DIR%deploy\windows-setup-assistant.ps1"
set "FETCH_PS1=%SCRIPT_DIR%deploy\bootstrap-fetch.ps1"
set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "REPO_WEB=https://github.com/Otaconskeep/otacons-ai-ecosystem"
set "DEBUG="
set "MODE="
set "PASSTHRU="

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

REM --- argument modes ---
:PARSE
if "%~1"=="" goto PARSE_DONE
if /I "%~1"=="--debug" (
  set "DEBUG=1"
  shift
  goto PARSE
)
if /I "%~1"=="-debug" (
  set "DEBUG=1"
  shift
  goto PARSE
)
if /I "%~1"=="--status" set "MODE=-Status"
if /I "%~1"=="-status" set "MODE=-Status"
if /I "%~1"=="--diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="-diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="--open" set "MODE=-Open"
if /I "%~1"=="-open" set "MODE=-Open"
if /I "%~1"=="--resume" set "MODE=-Resume"
if /I "%~1"=="-resume" set "MODE=-Resume"
shift
goto PARSE
:PARSE_DONE

call :LOG "==== install_otacon.bat start MODE=%MODE% DEBUG=%DEBUG% SCRIPT_DIR=%SCRIPT_DIR% ===="

if defined DEBUG (
  echo [DEBUG] LOGFILE=%LOGFILE%
  echo [DEBUG] ASSISTANT=%ASSISTANT%
  echo [DEBUG] MODE=%MODE%
)

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

:ENSURE_LOOP
call :ENSURE_ASSISTANT
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" (
  call :SHOW_DOWNLOAD_FAILED !RC! "downloading otaconskeep setup assistant"
  if /I "!CHOICE!"=="R" goto ENSURE_LOOP
  exit /b 1
)

if defined DEBUG echo [DEBUG] powershell -File "%ASSISTANT%" %MODE% ...
call :LOG "launching assistant MODE=%MODE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ASSISTANT%" %MODE% -RepoRoot "%SCRIPT_DIR:~0,-1%" -Branch "%BRANCH%"
set "RC=!ERRORLEVEL!"
call :LOG "assistant exit=!RC!"

REM Status/diagnostics/open success paths may exit 0 without pause — OK.
REM Any failure: keep this window alive (assistant may already have R/O/X).
if not "!RC!"=="0" (
  echo.
  echo ============================================================
  echo  SETUP WINDOW STAYING OPEN
  echo ============================================================
  echo  Setup helper exit code: !RC!
  echo  Log: %LOGFILE%
  echo.
  echo  If you already answered R/O/X above, press a letter key to close.
  echo  If the window flashed with no menu, the failure is in the log.
  echo ============================================================
  if defined DEBUG echo [DEBUG] never auto-exit on failure
  pause >nul
)

exit /b !RC!

REM ------------------------------------------------------------
:LOG
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] %~1
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
echo  powershell blocked by policy
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
  start "" explorer.exe "%LOG_DIR%"
  goto DF_CHOICE
)
if /I "!CHOICE!"=="R" exit /b 0
if /I "!CHOICE!"=="X" exit /b 0
goto DF_CHOICE

:ENSURE_ASSISTANT
if exist "%ASSISTANT%" (
  for %%A in ("%ASSISTANT%") do if %%~zA GEQ 40 (
    call :LOG "assistant present"
    exit /b 0
  )
)

echo.
echo ============================================================
echo  OTACONSKEEP SETUP
echo ============================================================
echo  Downloading setup files ^(first run only^)...
echo  Do not close this window.
echo  source
echo    %REPO_WEB%
echo ============================================================
echo.
call :LOG "ENSURE_ASSISTANT downloading deploy scripts"

if not exist "%SCRIPT_DIR%deploy" mkdir "%SCRIPT_DIR%deploy" >nul 2>&1

REM Prefer bootstrap-fetch.ps1 when already on disk (zip / prior fetch)
if exist "%FETCH_PS1%" (
  for %%A in ("%FETCH_PS1%") do if %%~zA GEQ 40 goto RUN_FETCH
)

REM Need helper: curl then PowerShell — capture every exit code
where curl.exe >nul 2>&1
if not errorlevel 1 (
  call :LOG "curl helper bootstrap-fetch.ps1"
  echo  [0/n] preparing download helper
  echo  status
  echo    downloading...
  curl.exe -fsSL --connect-timeout 20 --max-time 120 -o "%FETCH_PS1%" "%RAW%/deploy/bootstrap-fetch.ps1" >>"%LOGFILE%" 2>&1
  set "RC=!ERRORLEVEL!"
  call :LOG "curl helper exit=!RC!"
)

if not exist "%FETCH_PS1%" (
  call :LOG "powershell helper bootstrap-fetch.ps1"
  echo  status
  echo    downloading via PowerShell...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop'; $out='%FETCH_PS1%'; $url='%RAW%/deploy/bootstrap-fetch.ps1'; $log='%LOGFILE%';" ^
    "try {" ^
    "  Add-Content $log ('['+(Get-Date -Format o)+'] GET '+$url);" ^
    "  Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 120;" ^
    "  if(-not (Test-Path $out) -or ((Get-Item $out).Length -lt 40)){ throw 'helper too small' };" ^
    "  exit 0" ^
    "} catch { Add-Content $log ('ERROR '+$_.Exception.Message); Write-Host $_.Exception.Message; exit 1 }"
  set "RC=!ERRORLEVEL!"
  call :LOG "ps helper exit=!RC!"
  if not "!RC!"=="0" exit /b !RC!
)

if not exist "%FETCH_PS1%" (
  call :LOG "helper still missing"
  exit /b 2
)

:RUN_FETCH
echo  status
echo    downloading...
if defined DEBUG echo [DEBUG] -File "%FETCH_PS1%" -Manifest deploy
REM Visible on console; script also appends to installer.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -DestRoot "%SCRIPT_DIR:~0,-1%" -RawBase "%RAW%" -LogFile "%LOGFILE%" -Manifest deploy %DEBUG_SWITCH%
set "RC=!ERRORLEVEL!"
call :LOG "bootstrap-fetch deploy exit=!RC!"
if not "!RC!"=="0" exit /b !RC!

if not exist "%ASSISTANT%" (
  call :LOG "assistant missing after fetch"
  exit /b 2
)
for %%A in ("%ASSISTANT%") do if %%~zA LSS 40 (
  call :LOG "assistant too small"
  exit /b 2
)
echo  status
echo    verifying files... OK
exit /b 0
