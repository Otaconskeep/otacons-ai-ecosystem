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

## Installer rule: versioned bundle, not “file exists”

Installer-owned files under `%LOCALAPPDATA%\OtaconsKeep\installer` are **not** valid just because they exist. They are valid only when they match the expected `release.json` commit/hash.

- Public Setup must **always** refresh `deploy/bootstrap-fetch.ps1` (atomic temp download + replace) before running it.
- `bootstrap-fetch.ps1` must always replace the current installer bundle (assistant, repair, `wsl-bash-file.ps1`, revision pin, etc.). Never “if exists, skip”.
- After refresh, prove the **installed** `repair-otacon-core.ps1` uses `Invoke-OtaconWslBashFile` and does **not** still contain `bash -lc $bash`.
- Rebuild bundle metadata with `python3 deploy/build-release-manifest.py` when cutting an installer change.

## Packaging rule: hash published bytes only

`release.json` SHA256 values must be computed from the **exact bytes** GitHub raw serves (and Setup downloads).

1. Finalize artifact encoding on disk (`.bat` = UTF-8 **without** BOM + CRLF; `deploy/*.ps1` = UTF-8 **with** BOM + CRLF).
2. Store those exact bytes in git (`binary` in `.gitattributes` — never `text eol=crlf` for installer scripts).
3. Hash those bytes into `release.json`.
4. Downloader verifies **raw** downloaded bytes against the manifest.
5. Only after verification may optional local normalization run (its hash may differ without failing).

Never hash a post-normalization representation and verify a pre-normalization download.
