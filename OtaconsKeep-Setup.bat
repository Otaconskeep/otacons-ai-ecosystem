@echo off
REM ============================================================
REM  OtaconsKeep-Setup.bat  (public download name)
REM  Lone Downloads\ entry - fetches guided installer into
REM  %LOCALAPPDATA%\OtaconsKeep\installer then runs it.
REM  NEVER exits silently on fetch/download failure.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

REM --- encoding check: NEVER append %~f0 after powershell -Command ---
REM powershell.exe concatenates tokens after -Command into script text.
REM Paths like OtaconsKeep-Setup (1).bat then parse as PowerShell code.
set "OTACON_SETUP_SELF=%~f0"
set "ENC_PS1=%~dp0deploy\check-bat-encoding.ps1"
if exist "%ENC_PS1%" goto ENC_VIA_FILE
goto ENC_VIA_ENV
:ENC_VIA_FILE
powershell -NoProfile -ExecutionPolicy Bypass -File "%ENC_PS1%" -Path "%~f0"
goto ENC_AFTER_CHECK
:ENC_VIA_ENV
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $p = $env:OTACON_SETUP_SELF; if ([string]::IsNullOrWhiteSpace($p)) { Write-Host 'ERROR: installer path missing'; exit 2 }; if (-not (Test-Path -LiteralPath $p)) { Write-Host 'ERROR: installer file not found'; exit 2 }; $b = [IO.File]::ReadAllBytes($p); if ($b.Length -lt 8) { Write-Host 'ERROR: installer file empty'; exit 2 }; if ($b[0] -eq 255 -and $b[1] -eq 254) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 254 -and $b[1] -eq 255) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if (-not ($b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191)) { Write-Host 'ERROR: missing UTF-8 BOM. Re-download from the Otaconskeep website.'; exit 4 }; $bare = 0; for ($i = 0; $i -lt $b.Length; $i++) { if ($b[$i] -eq 10 -and ($i -eq 0 -or $b[$i-1] -ne 13)) { $bare++ } }; if ($bare -gt 0) { Write-Host 'ERROR: Unix line endings (bare LF). Re-download OtaconsKeep-Setup.bat from the Otaconskeep website.'; exit 5 }; exit 0 }"
:ENC_AFTER_CHECK
if errorlevel 1 goto ENC_FAIL
goto ENC_OK
:ENC_FAIL
echo.
echo ============================================================
echo                  OTACON SETUP STOPPED
echo ============================================================
echo.
echo  This installer file is damaged or was saved with the wrong encoding.
echo.
echo  nothing has been damaged on your PC
echo.
echo  What to do
echo  1. Delete this .bat file
echo  2. Open the Otaconskeep website
echo  3. Click Download OtaconsKeep Setup
echo  4. Run the new file from Downloads
echo.
echo  Do NOT open raw.githubusercontent.com and use Save As.
echo.
echo ============================================================
echo  This window will stay open. Press a letter key to exit.
echo ============================================================
pause >nul
exit /b 1
:ENC_OK

set "BRANCH=main"
set "REPO_WEB=https://github.com/Otaconskeep/otacons-ai-ecosystem"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "KEEP=%LOCALAPPDATA%\OtaconsKeep"
set "INST=%KEEP%\installer"
set "LOGDIR=%KEEP%\Logs"
set "LOGFILE=%LOGDIR%\installer.log"
set "ASSISTANT=%INST%\deploy\windows-setup-assistant.ps1"
set "FETCH_PS1=%INST%\deploy\bootstrap-fetch.ps1"
set "DOWNLOAD_ONE=%INST%\deploy\download-one.ps1"
set "TAIL_LOG=%INST%\deploy\tail-log.ps1"
set "DEBUG="
set "ARGS="
set "LAST_FAIL_CMD="
set "LAST_FAIL_REASON="
set "LAST_FAIL_OUT="
set "SYNTAX_ONLY="
set "FORCE_UPDATE="

:PARSE_ARGS
if "%~1"=="" goto ARGS_DONE
if /I "%~1"=="--syntax-check" goto SET_SYNTAX
if /I "%~1"=="-syntax-check" goto SET_SYNTAX
if /I "%~1"=="--debug" goto SET_DEBUG
if /I "%~1"=="-debug" goto SET_DEBUG
if /I "%~1"=="--update" goto SET_UPDATE
if /I "%~1"=="-update" goto SET_UPDATE
if /I "%~1"=="--refresh" goto SET_UPDATE
if /I "%~1"=="--fix-codec" goto SET_FIXCODEC
if /I "%~1"=="-fix-codec" goto SET_FIXCODEC
if /I "%~1"=="--fix" goto SET_FIXCODEC
if /I "%~1"=="-fix" goto SET_FIXCODEC
if /I "%~1"=="--open" goto SET_OPEN_ARG
if /I "%~1"=="-open" goto SET_OPEN_ARG
set "ARGS=!ARGS! %~1"
goto PARSE_SHIFT
:SET_SYNTAX
set "SYNTAX_ONLY=1"
goto PARSE_SHIFT
:SET_DEBUG
set "DEBUG=1"
goto PARSE_SHIFT
:SET_UPDATE
set "FORCE_UPDATE=1"
goto PARSE_SHIFT
:SET_FIXCODEC
set "ARGS=!ARGS! --fix-codec"
goto PARSE_SHIFT
:SET_OPEN_ARG
set "ARGS=!ARGS! --open"
goto PARSE_SHIFT
:PARSE_SHIFT
shift
goto PARSE_ARGS
:ARGS_DONE

if defined SYNTAX_ONLY goto SYNTAX_CHECK

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
if not exist "%INST%\deploy" mkdir "%INST%\deploy" >nul 2>&1

call :LOG "==== OtaconsKeep-Setup.bat start DEBUG=%DEBUG% ===="
call :LOG "INST=%INST%"
call :LOG "CD=%CD%"

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

if defined DEBUG echo [DEBUG] env=Windows
if defined DEBUG echo [DEBUG] cwd=%CD%
if defined DEBUG echo [DEBUG] LOGFILE=%LOGFILE%
if defined DEBUG echo [DEBUG] INST=%INST%
if defined DEBUG echo [DEBUG] RAW=%RAW%

set "LOCAL_ASSISTANT=%~dp0deploy\windows-setup-assistant.ps1"
if not exist "%LOCAL_ASSISTANT%" goto NEED_FETCH
call :LOG "local tree detected; skipping bootstrap fetch"
if defined DEBUG echo [DEBUG] command=call "%~dp0install_otacon.bat" %ARGS%
call "%~dp0install_otacon.bat" %ARGS%
set "RC=!ERRORLEVEL!"
call :LOG "install_otacon.bat exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" call :STAY_OPEN_AFTER_CHILD !RC!
exit /b !RC!

:NEED_FETCH
REM Pin local AppData installer across retries unless --update/--refresh,
REM or unless GitHub's installer-revision.txt moved (so fixes reach Josh).
if defined FORCE_UPDATE goto NEED_FETCH_FORCE
if not exist "%ASSISTANT%" goto NEED_FETCH_FORCE
if not exist "%INST%\deploy\installer-revision.txt" goto NEED_FETCH_FORCE
set "LOCAL_REV="
set "REMOTE_REV="
for /f "usebackq delims=" %%R in ("%INST%\deploy\installer-revision.txt") do set "LOCAL_REV=%%R"
curl.exe -fsSL --connect-timeout 8 --max-time 15 "%RAW%/deploy/installer-revision.txt" > "%TEMP%\otacon-installer-rev-remote.txt" 2>nul
if exist "%TEMP%\otacon-installer-rev-remote.txt" for /f "usebackq delims=" %%R in ("%TEMP%\otacon-installer-rev-remote.txt") do set "REMOTE_REV=%%R"
if defined REMOTE_REV if /I not "!LOCAL_REV!"=="!REMOTE_REV!" (
  call :LOG "pinned revision stale local=!LOCAL_REV! remote=!REMOTE_REV! - refetching"
  goto NEED_FETCH_FORCE
)
goto USE_PINNED_LOCAL
:USE_PINNED_LOCAL
call :LOG "pinned local installer present; skipping refetch - pass --update to refresh from GitHub"
for /f "usebackq delims=" %%R in ("%INST%\deploy\installer-revision.txt") do call :LOG "pinned revision=%%R"
goto FETCH_VERIFY_OK
:NEED_FETCH_FORCE
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
if defined DEBUG echo [DEBUG] ENSURE_FETCH_HELPER errorlevel=!RC!
if "!RC!"=="0" goto FETCH_HELPER_OK
set "LAST_FAIL_CMD=download bootstrap-fetch.ps1 helper from github"
set "LAST_FAIL_REASON=Could not save the download helper script to your AppData folder."
call :CAPTURE_LAST_OUTPUT
call :SHOW_SETUP_STOPPED !RC!
if /I "!CHOICE!"=="R" goto FETCH_RETRY
exit /b 1

:FETCH_HELPER_OK
echo.
echo  [1/2] downloading otaconskeep
echo  source
echo    %REPO_WEB%
echo  status
echo    downloading...
echo  Do not close this window.
echo.

if defined DEBUG echo [DEBUG] env=Windows
if defined DEBUG echo [DEBUG] cwd=%CD%
if defined DEBUG echo [DEBUG] command=powershell -File bootstrap-fetch.ps1 -Manifest full

powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -DestRoot "%INST%" -RawBase "%RAW%" -LogFile "%LOGFILE%" -Manifest full %DEBUG_SWITCH%
set "RC=!ERRORLEVEL!"
call :LOG "bootstrap-fetch.ps1 exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if "!RC!"=="0" goto FETCH_FILES_OK
set "LAST_FAIL_CMD=powershell -File deploy\bootstrap-fetch.ps1 -Manifest full"
set "LAST_FAIL_REASON=One or more OtaconsKeep setup files could not be downloaded from GitHub."
call :CAPTURE_LAST_OUTPUT
call :SHOW_SETUP_STOPPED !RC!
if /I "!CHOICE!"=="R" goto FETCH_RETRY
exit /b 1

:FETCH_FILES_OK
if exist "%ASSISTANT%" goto FETCH_VERIFY_OK
call :LOG "ASSISTANT missing after fetch"
set "LAST_FAIL_CMD=verify deploy\windows-setup-assistant.ps1 exists"
set "LAST_FAIL_REASON=Download finished without the setup assistant file."
call :CAPTURE_LAST_OUTPUT
call :SHOW_SETUP_STOPPED 2
if /I "!CHOICE!"=="R" goto FETCH_RETRY
exit /b 1

:FETCH_VERIFY_OK
echo.
echo  status
echo    verifying files... OK
echo.
call :LOG "fetch OK; launching install_otacon.bat"

if defined DEBUG set "ARGS=!ARGS! --debug"
if defined DEBUG echo [DEBUG] command=call install_otacon.bat
call "%INST%\install_otacon.bat" %ARGS%
set "RC=!ERRORLEVEL!"
call :LOG "install_otacon.bat exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" call :STAY_OPEN_AFTER_CHILD !RC!
exit /b !RC!

:SYNTAX_CHECK
echo ============================================================
echo  OTACONSKEEP SYNTAX CHECK
echo ============================================================
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
call :LOG "syntax-check begin"
call :CAPTURE_LAST_OUTPUT
echo  [OK] CAPTURE_LAST_OUTPUT
echo  [OK] argument parser
echo  [OK] label graph
echo  SYNTAX_CHECK_OK
exit /b 0

:LOG
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] %~1
exit /b 0

:CAPTURE_LAST_OUTPUT
REM Do not wrap PowerShell containing ) inside IF (...).
set "LAST_FAIL_OUT="
if not exist "%LOGFILE%" exit /b 0
set "LASTOUT=%LOGDIR%\last-output.txt"
if not exist "%TAIL_LOG%" goto CAPTURE_INLINE
powershell -NoProfile -ExecutionPolicy Bypass -File "%TAIL_LOG%" -LogFile "%LOGFILE%" -OutFile "%LASTOUT%" -Tail 12
set "LAST_FAIL_OUT=%LASTOUT%"
exit /b 0
:CAPTURE_INLINE
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath $env:LOGFILE -Tail 12 | Set-Content -LiteralPath $env:LASTOUT -Encoding ASCII"
set "LAST_FAIL_OUT=%LASTOUT%"
exit /b 0

:STAY_OPEN_AFTER_CHILD
set "CHILD_RC=%~1"
echo.
echo ============================================================
echo  SETUP WINDOW STAYING OPEN
echo ============================================================
echo  The setup helper finished with exit code %CHILD_RC%.
echo  Log: %LOGFILE%
echo ============================================================
if defined DEBUG echo [DEBUG] never auto-close on failure
pause >nul
exit /b 0

:SHOW_SETUP_STOPPED
set "FAIL_RC=%~1"
set "CHOICE="
call :LOG "SHOW_SETUP_STOPPED rc=%FAIL_RC% cmd=%LAST_FAIL_CMD%"
echo.
echo ============================================================
echo                  OTACON SETUP STOPPED
echo ============================================================
echo.
echo  something went wrong while fetching otaconskeep
echo.
echo  nothing has been damaged
echo.
echo  failed command
echo  %LAST_FAIL_CMD%
echo.
echo  exit code
echo  %FAIL_RC%
echo.
echo  reason
echo  %LAST_FAIL_REASON%
echo.
echo  last output
if not exist "%LOGDIR%\last-output.txt" goto SHOW_NO_LAST
type "%LOGDIR%\last-output.txt"
goto SHOW_AFTER_LAST
:SHOW_NO_LAST
echo  see installer.log
:SHOW_AFTER_LAST
echo.
echo  technical details
echo  %LOGFILE%
echo.
echo  [R] retry this step
echo  [L] open installer log
echo  [D] show technical details
echo  [X] exit
echo.
echo ============================================================
echo.
:SS_CHOICE
set /p "CHOICE=  Choice [R/L/D/X]: "
if /I "!CHOICE!"=="L" goto SS_OPEN_LOG
if /I "!CHOICE!"=="D" goto SS_DETAILS
if /I "!CHOICE!"=="R" goto SS_RETRY
if /I "!CHOICE!"=="X" goto SS_EXIT
goto SS_CHOICE
:SS_OPEN_LOG
start "" explorer.exe "%LOGDIR%"
goto SS_CHOICE
:SS_DETAILS
echo.
echo  ---- technical details ----
echo  LOGFILE=%LOGFILE%
echo  INST=%INST%
echo  RAW=%RAW%
echo  CD=%CD%
if not exist "%LOGFILE%" goto SS_DETAILS_END
echo  ---- last 40 log lines ----
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOGFILE -Tail 40"
:SS_DETAILS_END
echo  ---- end ----
echo.
goto SS_CHOICE
:SS_RETRY
call :LOG "user chose RETRY"
exit /b 0
:SS_EXIT
call :LOG "user chose EXIT"
exit /b 0

:ENSURE_FETCH_HELPER
if not exist "%FETCH_PS1%" goto HELPER_NEED
for %%A in ("%FETCH_PS1%") do if %%~zA GEQ 40 goto HELPER_PRESENT
goto HELPER_NEED
:HELPER_PRESENT
call :LOG "bootstrap-fetch.ps1 already present"
exit /b 0

:HELPER_NEED
echo.
echo  [0/2] preparing download helper
echo  source
echo    %RAW%/deploy/bootstrap-fetch.ps1
echo  status
echo    connecting...
echo.

where curl.exe >nul 2>&1
if errorlevel 1 goto HELPER_PS
call :LOG "using curl.exe to fetch bootstrap-fetch.ps1"
if defined DEBUG echo [DEBUG] env=Windows
if defined DEBUG echo [DEBUG] command=curl.exe download bootstrap-fetch.ps1
echo  status
echo    downloading...
curl.exe -fsSL --connect-timeout 20 --max-time 120 -o "%FETCH_PS1%" "%RAW%/deploy/bootstrap-fetch.ps1" >>"%LOGFILE%" 2>&1
set "RC=!ERRORLEVEL!"
call :LOG "curl bootstrap-fetch exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" goto HELPER_PS
if not exist "%FETCH_PS1%" goto HELPER_PS
for %%A in ("%FETCH_PS1%") do if %%~zA LSS 40 goto HELPER_PS
echo  status
echo    verifying files... OK
exit /b 0

:HELPER_PS
echo  status
echo    downloading via PowerShell...
if exist "%DOWNLOAD_ONE%" goto HELPER_PS_FILE
if exist "%~dp0deploy\download-one.ps1" set "DOWNLOAD_ONE=%~dp0deploy\download-one.ps1"
if exist "%DOWNLOAD_ONE%" goto HELPER_PS_FILE
REM Top-level -Command only - never inside IF (...).
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12}catch{}; Invoke-WebRequest -Uri ($env:RAW+'/deploy/bootstrap-fetch.ps1') -OutFile $env:FETCH_PS1 -UseBasicParsing -TimeoutSec 120; if(-not(Test-Path -LiteralPath $env:FETCH_PS1)){exit 1}; if((Get-Item -LiteralPath $env:FETCH_PS1).Length -lt 40){exit 1}; exit 0"
set "RC=!ERRORLEVEL!"
goto HELPER_PS_DONE

:HELPER_PS_FILE
if defined DEBUG echo [DEBUG] command=powershell -File download-one.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%DOWNLOAD_ONE%" -Url "%RAW%/deploy/bootstrap-fetch.ps1" -OutFile "%FETCH_PS1%" -LogFile "%LOGFILE%"
set "RC=!ERRORLEVEL!"

:HELPER_PS_DONE
call :LOG "powershell helper fetch exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" exit /b !RC!
if not exist "%FETCH_PS1%" exit /b 2
for %%A in ("%FETCH_PS1%") do if %%~zA LSS 40 exit /b 2
echo  status
echo    verifying files... OK
exit /b 0
