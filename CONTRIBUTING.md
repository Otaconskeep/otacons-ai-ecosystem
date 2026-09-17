# Contributing

Contributions are welcome under the project's selected license. Please keep public code generic and never submit credentials, private deployment state, runtime databases, models, voices, or personal data.

Otacon is Designed & Engineered by Antonio Garcia.

## Installer rule: Windows → WSL Bash transport

Any nontrivial Bash script that crosses Windows → WSL **must** be written to a temporary `.sh` file and executed as a file.

- Use `deploy/wsl-bash-file.ps1` (`Invoke-OtaconWslBashFile`).
- Temp file: UTF-8 **without** BOM, LF only (no CRLF).
- Convert the Windows path with `wslpath`, run `bash -n` first, then `bash <file>`.
- Capture `$LASTEXITCODE` immediately after each `wsl.exe` call.
- **Never** pass multiline Bash through `bash -c` / `bash -lc` as one command-line string.

Short one-liners may still use `bash -lc` when they contain no embedded quotes/newlines that PowerShell can mangle. When in doubt, use the file transport.
