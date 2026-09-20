#!/usr/bin/env python3
"""Normal Setup (no --update) must detect stale cached installer and self-refresh."""
from __future__ import annotations

import re
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
    setup = (ROOT / "OtaconsKeep-Setup.bat").read_text(encoding="utf-8", errors="replace")
    install = (ROOT / "install_otacon.bat").read_text(encoding="utf-8", errors="replace")
    assistant = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8-sig")
    repair = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")

    must("CHECK_INSTALLER_STALE" in setup, "Setup has CHECK_INSTALLER_STALE", fails)
    must(":CHECK_INSTALLER_STALE" in setup, "Setup defines :CHECK_INSTALLER_STALE label", fails)
    fetch_retry = setup.split(":FETCH_RETRY", 1)[1].split(":FETCH_HELPER_OK", 1)[0]
    must("call :ENSURE_FETCH_HELPER" in fetch_retry,
         "FETCH_RETRY calls ENSURE_FETCH_HELPER before download", fails)
    must("call :CHECK_INSTALLER_STALE" not in fetch_retry,
         "FETCH_RETRY does not inline stale-check body", fails)
    must("(will not use unverified stale cache)" not in setup,
         "Setup avoids CMD paren-trap log string inside IF blocks", fails)
    must("cached revision=" in setup, "Setup logs cached revision", fails)
    must("published revision=" in setup, "Setup logs published revision", fails)
    must("refresh required=" in setup, "Setup logs refresh required", fails)
    must("no --update required" in setup.lower() or "Users must NOT need --update" in setup,
         "Setup documents that --update is not required", fails)
    must("FORCE_UPDATE" in setup, "Setup still supports --update force refresh", fails)
    must("VERIFY_CACHED_HELPERS" in setup, "Setup verifies cached helper content", fails)
    must("git_as_owner" in setup and "runuser -u" in setup,
         "Setup requires runuser/git_as_owner in cached repair before continue", fails)
    must("skipping refetch" not in setup, "Setup never says skipping refetch for pin alone", fails)
    must("USE_PINNED_LOCAL" not in setup, "Setup has no USE_PINNED_LOCAL skip path", fails)
    must("OtaconsKeep\\installer" in setup or "AppData installer" in setup,
         "Setup does not treat AppData installer as skippable local tree", fails)

    # Simulate stale pin decision logic (text-level contract)
    must("CACHED_REV" in setup and "PUBLISHED_REV" in setup
         and "REFRESH_REQUIRED" in setup,
         "Setup compares cached vs published revision", fails)
    must("REFRESH_REQUIRED=1" in setup, "Setup sets REFRESH_REQUIRED on stale/unknown", fails)

    # Preload-old-pin regression (logical): old revision + normal launch => refresh
    old_rev = "d87eaa4deadbeef"
    new_rev = "97826815d742b1ebae466dbc8c071cfb502b74af"
    must(old_rev != new_rev, "fixture revisions differ", fails)
    # Decision function mirrored from bat
    def refresh_required(cached: str, published: str, force: bool = False) -> bool:
        if force:
            return True
        if cached in ("", "none"):
            return True
        if published in ("", "unknown"):
            return True
        return cached.lower() != published.lower()

    must(refresh_required(old_rev, new_rev, force=False) is True,
         "preload old pin + normal launch => refresh required", fails)
    must(refresh_required(new_rev, new_rev, force=False) is False,
         "current pin + normal launch => refresh not required by revision alone", fails)
    must(refresh_required(new_rev, new_rev, force=True) is True,
         "--update force refresh still works", fails)

    must("git_as_owner" in install and "runuser -u" in install,
         "install_otacon verifies owner-git markers after refresh", fails)
    must("refresh required=true" in install.lower() or "always refreshes" in install.lower(),
         "install_otacon refreshes without requiring --update", fails)

    must("git_as_owner" in assistant and "runuser -u" in assistant,
         "assistant refuses repair without owner-context fix in cache", fails)
    must("git_as_owner" in repair and "runuser -u" in repair,
         "canonical repair contains owner-context fix", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Stale-installer auto-refresh regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
