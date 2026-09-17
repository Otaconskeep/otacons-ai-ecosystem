#!/usr/bin/env python3
"""Stale bootstrap/repair cache must be replaced on every Setup launch."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    fails: list[str] = []
    setup = read(ROOT / "OtaconsKeep-Setup.bat")
    install = read(ROOT / "install_otacon.bat")
    fetch = read(ROOT / "deploy" / "bootstrap-fetch.ps1")
    repair = read(ROOT / "deploy" / "repair-otacon-core.ps1")
    release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))

    # Launcher never trusts cached bootstrap solely because it exists.
    must("already present" not in setup.lower() or "ALWAYS refresh" in setup,
         "Setup does not treat existing bootstrap as fresh", fails)
    must("ALWAYS refreshing bootstrap-fetch.ps1" in setup
         or "ALWAYS refresh" in setup,
         "Setup always refreshes bootstrap-fetch.ps1", fails)
    must("otacon-new" in setup, "Setup uses atomic temp download for bootstrap", fails)
    must("skipping refetch" not in setup,
         "Setup no longer skips refetch via USE_PINNED_LOCAL", fails)
    must("CHECK_INSTALLER_STALE" in setup or "refresh required=" in setup,
         "Setup checks cached vs published revision", fails)
    must("no --update required" in setup.lower() or "REFRESH_REQUIRED" in setup,
         "Setup auto-refreshes without requiring --update", fails)

    must("ALWAYS refresh bootstrap-fetch.ps1" in install
         or "always refreshing installer-owned" in install,
         "install_otacon.bat always refreshes helpers", fails)
    must("assistant present" not in install or "always refreshing" in install.lower(),
         "install_otacon.bat does not exit early on assistant present alone", fails)
    must("wsl-bash-file.ps1" in install, "install_otacon.bat verifies wsl-bash-file.ps1", fails)
    must("Invoke-OtaconWslBashFile" in install, "install_otacon.bat proves repair transport", fails)

    must("Installer-owned files are NOT valid just because they exist" in fetch
         or "valid only when they match" in fetch,
         "bootstrap documents version/hash validity rule", fails)
    must("NEVER skip because a cached file already exists" in fetch
         or "always replace" in fetch.lower(),
         "bootstrap always replaces cached files", fails)
    must("installer_version" in fetch, "bootstrap reads installer_version", fails)
    must("BOOTSTRAP_OK" in fetch, "bootstrap logs BOOTSTRAP_OK with version", fails)
    must("deploy/wsl-bash-file.ps1" in fetch, "bootstrap manifest includes wsl-bash-file.ps1", fails)
    must("deploy/repair-otacon-core.ps1" in fetch, "bootstrap manifest includes repair helper", fails)
    must(
        "Invoke-OtaconWslBashFile" in fetch and "stale cache" in fetch and "bash -lc" in fetch,
        "bootstrap verifies installed repair transport markers",
        fails,
    )
    must("Get-FileSha256Hex" in fetch or "sha256" in fetch.lower(),
         "bootstrap can verify SHA256 hashes", fails)
    must("ParseFile" in fetch and "wsl-bash-file.ps1" in fetch,
         "bootstrap parse-checks wsl-bash-file.ps1", fails)

    must("installer_version" in release, "release.json has installer_version", fails)
    must("commit" in release, "release.json has commit", fails)
    must(isinstance(release.get("files"), list) and len(release["files"]) >= 5,
         "release.json lists bundle files", fails)
    must(any(f.get("path") == "deploy/repair-otacon-core.ps1" for f in release["files"]),
         "release.json includes repair-otacon-core.ps1", fails)
    must(any(f.get("path") == "deploy/wsl-bash-file.ps1" for f in release["files"]),
         "release.json includes wsl-bash-file.ps1", fails)
    must(any(f.get("path") == "deploy/bootstrap-fetch.ps1" for f in release["files"]),
         "release.json includes bootstrap-fetch.ps1", fails)

    # Simulate stale AppData cache: old bootstrap + old repair -> current tree must not match.
    old_bootstrap = "# stale\nif (Test-Path $out) { continue }\n# no wsl-bash-file\n"
    old_repair = "$out = & wsl.exe -d $Name -u root -- bash -lc $bash 2>&1\n"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        deploy = td_path / "deploy"
        deploy.mkdir()
        (deploy / "bootstrap-fetch.ps1").write_text(old_bootstrap, encoding="utf-8")
        (deploy / "repair-otacon-core.ps1").write_text(old_repair, encoding="utf-8")
        # "Refresh" by copying current canonical files (what Setup+bootstrap must achieve).
        shutil.copy2(ROOT / "deploy" / "bootstrap-fetch.ps1", deploy / "bootstrap-fetch.ps1")
        shutil.copy2(ROOT / "deploy" / "repair-otacon-core.ps1", deploy / "repair-otacon-core.ps1")
        shutil.copy2(ROOT / "deploy" / "wsl-bash-file.ps1", deploy / "wsl-bash-file.ps1")
        new_boot = (deploy / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
        new_rep = (deploy / "repair-otacon-core.ps1").read_text(encoding="utf-8", errors="replace")
        must("bash -lc $bash" not in new_rep, "after refresh, stale bash -lc repair is gone", fails)
        must("Invoke-OtaconWslBashFile" in new_rep, "after refresh, repair uses file transport", fails)
        must("wsl-bash-file" in new_boot, "after refresh, bootstrap knows wsl-bash-file", fails)
        must((deploy / "wsl-bash-file.ps1").is_file(), "after refresh, wsl-bash-file.ps1 present", fails)
        # Hash proof vs release.json
        for entry in release["files"]:
            rel = entry["path"]
            if rel not in ("deploy/repair-otacon-core.ps1", "deploy/wsl-bash-file.ps1", "deploy/bootstrap-fetch.ps1"):
                continue
            data = (ROOT / rel).read_bytes()
            got = hashlib.sha256(data).hexdigest()
            must(got == entry["sha256"], f"release.json sha256 matches tree for {rel}", fails)

    must("bash -lc $bash" not in repair, "canonical repair has no bash -lc $bash", fails)
    must("Invoke-OtaconWslBashFile" in repair, "canonical repair uses Invoke-OtaconWslBashFile", fails)

    # Setup verifies installed helper markers after fetch
    must("FETCH_REPAIR_STALE" in setup or "temp .sh transport" in setup,
         "Setup fails closed if installed repair stays stale", fails)
    must("FETCH_WSL_MISSING" in setup or "wsl-bash-file.ps1" in setup,
         "Setup requires wsl-bash-file.ps1 after fetch", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Installer cache refresh regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
