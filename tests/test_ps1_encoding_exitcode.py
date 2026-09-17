#!/usr/bin/env python3
"""PowerShell 5.1-safe encoding + exit-code propagation contracts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []
    deploy = ROOT / "deploy"
    critical = [
        "repair-otacon-core.ps1",
        "windows-setup-assistant.ps1",
        "bootstrap-fetch.ps1",
        "fix-otacon-gpu.ps1",
        "wake-otacon.ps1",
    ]
    for name in critical:
        p = deploy / name
        raw = p.read_bytes()
        must(raw.startswith(b"\xef\xbb\xbf"), f"{name} has UTF-8 BOM", fails)
        text = raw[3:].decode("utf-8")
        must("\r\n" in text, f"{name} uses CRLF", fails)
        non_ascii = sorted({c for c in text if ord(c) > 127})
        must(len(non_ascii) == 0, f"{name} is ASCII-only (found {non_ascii[:5]})", fails)
        for bad in ("\u2014", "\u2260", "\u2018", "\u2019", "\u201c", "\u201d"):
            must(bad not in text, f"{name} has no Unicode punct U+{ord(bad):04X}", fails)

    assistant = (deploy / "windows-setup-assistant.ps1").read_text(encoding="utf-8-sig")
    fetch = (deploy / "bootstrap-fetch.ps1").read_text(encoding="utf-8-sig")
    repair = (deploy / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")

    must("function Test-OtaconPs1Parses" in assistant, "assistant has ParseFile preflight", fails)
    must("Parser]::ParseFile" in assistant, "assistant calls Language.Parser.ParseFile", fails)
    must("Start-Process -FilePath \"powershell.exe\"" in assistant
         or "Start-Process -FilePath 'powershell.exe'" in assistant,
         "assistant uses Start-Process for helper exit code", fails)
    repair_fn = assistant.split("function Invoke-OtaconCoreRepair")[1].split("function Test-OtaconIdentity")[0]
    must("Start-Process -FilePath \"powershell.exe\"" in repair_fn
         or "Start-Process -FilePath 'powershell.exe'" in repair_fn,
         "Invoke-OtaconCoreRepair uses Start-Process ExitCode", fails)
    must("$proc.ExitCode" in repair_fn, "Invoke-OtaconCoreRepair reads proc.ExitCode", fails)
    must("Test-OtaconPs1Parses" in repair_fn, "Invoke-OtaconCoreRepair runs parse preflight", fails)
    must("FixCodec UPDATE FAILED - propagating exit 1" in assistant
         or "exit 1" in assistant,
         "FixCodec propagates failure with exit 1", fails)
    must("normalized encoding BOM+CRLF" in fetch, "bootstrap normalizes .ps1 encoding after download", fails)
    must("Parser]::ParseFile" in fetch, "bootstrap parse-checks helpers after download", fails)
    must("APP_REV_OK=1" in repair and "APP_REV_BEFORE=" in repair, "repair still proves Linux revision", fails)

    # install_otacon.bat must preserve nonzero
    bat = (ROOT / "install_otacon.bat").read_text(encoding="utf-8", errors="replace")
    setup = (ROOT / "OtaconsKeep-Setup.bat").read_text(encoding="utf-8", errors="replace")
    must('if "!RC!"=="0" exit /b 0' in bat, "install_otacon.bat only auto-exits 0 on success", fails)
    must("exit /b !RC!" in bat, "install_otacon.bat can exit with helper RC", fails)
    must("exit /b !RC!" in setup, "Setup.bat propagates child RC", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("PS1 encoding / exit-code regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
