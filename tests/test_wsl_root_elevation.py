#!/usr/bin/env python3
"""Regression: password-protected sudo accounts must install via wsl -u root split."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = (ROOT / "install_otacon.sh").read_text(encoding="utf-8")
PS1 = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []

    # Simulated fresh Ubuntu: sudo requires password, no TTY from Windows.
    # Architecture requirements:
    must("OTACON_INSTALL_PHASE=privileged" in PS1 or 'Phase "privileged"' in PS1, "Windows schedules privileged phase", fails)
    must("-u root" in PS1 or '-AsUser "root"' in PS1, "Windows elevates with wsl -u root", fails)
    must("OTACON_TARGET_USER" in SH and "OTACON_TARGET_USER" in PS1, "target user passed for ownership", fails)
    must("resolve_target_user" in SH, "root phase resolves target user", fails)
    must('INSTALL_PHASE" == "user" && "${EUID' in SH or "user phase must not run as root" in SH, "user phase ownership guard", fails)
    must("PRIV_MARKER" in SH or "privileged-bootstrap.done" in SH, "privileged bootstrap marker", fails)
    must("SKIP_APT" in SH or "skipping apt in user" in SH.lower() or "Privileged bootstrap marker" in SH, "user phase skips apt", fails)
    must("Service draft" in SH or "SERVICE_DRAFT" in SH, "user writes service draft", fails)
    must("draft_owner" in SH or "Service draft owner" in SH, "finalize verifies draft ownership", fails)
    must("install -m 644" in SH, "finalize installs unit with install(1)", fails)

    # Must not hang waiting for sudo password in non-interactive auto path
    must("NEED_PRIVILEGED_HELPER" in SH, "detects missing TTY/sudo without blocking", fails)
    must("Cannot install system packages without a TTY or root" in SH, "fails fast instead of hanging on sudo", fails)
    must("[[ -t 0 ]]" in SH and "[[ -t 1 ]]" in SH, "TTY detection before interactive sudo", fails)

    # Cleanup / no persistent sudo weaken
    must("tee /etc/sudoers.d" not in SH and "tee /etc/sudoers.d" not in PS1, "never writes sudoers.d", fails)
    must("ALL=(ALL) NOPASSWD:ALL" not in PS1, "never instructs NOPASSWD:ALL", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} password-sudo regression(s) failed")
        return 1
    print("Password-protected sudo elevation regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
