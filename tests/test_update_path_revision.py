#!/usr/bin/env python3
"""Regression: installer update must prove Linux app revision changed.

installer updated ≠ application updated.
"""
from __future__ import annotations

import re
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
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
    repair = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8", errors="replace")
    assistant = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8", errors="replace")
    setup = (ROOT / "OtaconsKeep-Setup.bat").read_text(encoding="utf-8", errors="replace")

    must("deploy/repair-otacon-core.ps1" in fetch, "bootstrap full list includes repair-otacon-core.ps1", fails)
    must(
        'deploy/repair-otacon-core.ps1"' in fetch or "deploy/repair-otacon-core.ps1" in fetch,
        "repair helper listed for download",
        fails,
    )
    must("required helpers present including repair-otacon-core.ps1" in fetch
         or "MISSING REQUIRED" in fetch,
         "bootstrap verifies required helpers after download", fails)
    must("deploy/repair-otacon-core.ps1" in fetch.split("$deployOnly")[0] if "$deployOnly" in fetch else True,
         "repair in $full manifest region", fails)

    # deployOnly must also include repair
    m = re.search(r"\$deployOnly\s*=\s*@\((.*?)\)", fetch, re.S)
    must(m is not None and "repair-otacon-core.ps1" in m.group(1), "deployOnly includes repair-otacon-core.ps1", fails)

    must("APP_REV_BEFORE=" in repair, "repair logs APP_REV_BEFORE", fails)
    must("APP_REV_AFTER=" in repair, "repair logs APP_REV_AFTER", fails)
    must("APP_REV_TARGET=" in repair or "APP_REV_TARGET=" in repair.replace(" ", ""), "repair logs target", fails)
    must("APP_REV_OK=1" in repair, "repair emits APP_REV_OK", fails)
    must("APP_REV_FAIL=" in repair, "repair emits APP_REV_FAIL on mismatch", fails)
    must("CONTENT_PROOFS_OK=1" in repair, "repair requires content proofs", fails)
    must("PROOF_MEMORY_CONNECTION=" in repair, "repair proves memory thread-safety markers", fails)
    must("PROOF_NO_SCAN_NULL_PATCH=" in repair, "repair proves scan=null patch absent", fails)
    must("PROOF_THINKING_FINALLY=" in repair, "repair proves THINKING finally cleanup", fails)
    must("reset --hard" in repair, "repair hard-syncs git", fails)
    must("inline wake" not in repair.lower() or "NEVER" in repair, "repair does not soft-succeed on wake alone", fails)

    must("repair-otacon-core.ps1 missing - inline wake" not in assistant,
         "assistant no longer success-falls-back to inline wake", fails)
    must("UPDATE FAILED: repair-otacon-core.ps1 missing" in assistant
         or "repair-otacon-core.ps1 missing after fetch" in assistant,
         "assistant fails when repair helper missing", fails)
    must("Linux application revision not proven" in assistant
         or "Linux Otacon application did not update" in assistant,
         "READY path fails when Linux app not updated", fails)
    must('"$RawBase/deploy/repair-otacon-core.ps1"' not in assistant,
         "broken branchless RawBase repair URL removed", fails)
    must("Get-OtaconRawFileUrl" in assistant, "assistant builds raw URLs via Get-OtaconRawFileUrl", fails)
    must("Never omit the branch/ref" in assistant or "MUST include branch/ref" in assistant,
         "assistant documents branch/ref requirement", fails)

    must("repair-otacon-core.ps1" in setup, "Setup.bat checks for repair helper", fails)
    must("FETCH_REPAIR_MISSING" in setup or "missing repair-otacon-core" in setup.lower(),
         "Setup.bat fails fetch verify without repair helper", fails)
    must(
        "always refreshes installer bundle" in setup.lower()
        or "ALWAYS refreshing bootstrap-fetch.ps1" in setup
        or "FORCE_UPDATE" in setup,
        "Setup always refreshes installer bundle / bootstrap",
        fails,
    )

    # Content that Linux proofs look for must exist in tree
    mem = (ROOT / "core" / "memory.py").read_text(encoding="utf-8", errors="replace")
    wiz = (ROOT / "ui" / "wizard.js").read_text(encoding="utf-8", errors="replace")
    must("def connection(self)" in mem, "memory.py has connection()", fails)
    must("check_same_thread=False" not in mem.replace(" ", ""), "memory.py does not disable thread check", fails)
    must("repair: never block Codec on GPU scan" not in wiz, "wizard.js has no scan=null repair patch", fails)
    must("setCodecMode('thinking')" in wiz and "}finally{" in wiz, "wizard.js has thinking+finally", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Update-path revision regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
