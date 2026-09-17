#!/usr/bin/env python3
"""URL join contract: RawBase + Branch/ref + path (never omit ref → 404)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def join_raw(base: str, ref: str, rel: str) -> str:
    """Mirror of Get-OtaconRawFileUrl in windows-setup-assistant.ps1."""
    b = (base or "").strip().rstrip("/")
    r = (ref or "main").strip().strip("/")
    rel = (rel or "").strip().lstrip("/")
    if not b:
        b = "https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem"
    if b.endswith("/" + r):
        return f"{b}/{rel}"
    # strip trailing ref-like segment
    b2 = re.sub(r"/(main|master|[0-9a-f]{7,40}|v\d[\w.\-]*)$", "", b, flags=re.I)
    return f"{b2}/{r}/{rel}"


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []
    assistant = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8", errors="replace")
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
    install_bat = (ROOT / "install_otacon.bat").read_text(encoding="utf-8", errors="replace")

    must("function Get-OtaconRawFileUrl" in assistant, "Get-OtaconRawFileUrl exists", fails)
    must("Get-OtaconRawFileUrl -RelativePath \"deploy/repair-otacon-core.ps1\"" in assistant
         or "Get-OtaconRawFileUrl -RelativePath 'deploy/repair-otacon-core.ps1'" in assistant,
         "fallback uses Get-OtaconRawFileUrl for repair helper", fails)
    must('"$RawBase/deploy/repair-otacon-core.ps1"' not in assistant,
         "broken RawBase-only repair URL removed", fails)
    must("-RawBase \"%RAW%\"" in install_bat or '-RawBase "%RAW%"' in install_bat,
         "install_otacon.bat passes -RawBase to assistant", fails)

    must("deploy/repair-otacon-core.ps1" in fetch, "bootstrap manifest lists repair helper", fails)
    m_full = re.search(r"\$full\s*=\s*@\((.*?)\)", fetch, re.S)
    m_dep = re.search(r"\$deployOnly\s*=\s*@\((.*?)\)", fetch, re.S)
    must(m_full is not None and "repair-otacon-core.ps1" in m_full.group(1),
         "repair in $full manifest", fails)
    must(m_dep is not None and "repair-otacon-core.ps1" in m_dep.group(1),
         "repair in $deployOnly manifest", fails)

    repo = "https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem"
    rel = "deploy/repair-otacon-core.ps1"

    # main branch from repo-root RawBase
    u = join_raw(repo, "main", rel)
    must(u == f"{repo}/main/{rel}", f"main URL from repo root: {u}", fails)
    must("/main/deploy/repair-otacon-core.ps1" in u, "main URL contains /main/", fails)
    must(u != f"{repo}/{rel}", "main URL is not the 404 form without ref", fails)

    # RawBase already includes /main (Setup.bat style)
    u2 = join_raw(f"{repo}/main", "main", rel)
    must(u2 == f"{repo}/main/{rel}", f"idempotent when RawBase has /main: {u2}", fails)

    # alternate branch/ref
    u3 = join_raw(repo, "staging-fix", rel)
    must(u3 == f"{repo}/staging-fix/{rel}", f"alternate branch URL: {u3}", fails)

    # commit SHA ref
    sha = "6b5028b74bfefa1f98fb233fec1840838d529e75"
    u4 = join_raw(repo, sha, rel)
    must(u4 == f"{repo}/{sha}/{rel}", f"sha ref URL: {u4}", fails)

    # Prove live main URL is reachable from this host
    import urllib.request
    try:
        with urllib.request.urlopen(join_raw(repo, "main", rel), timeout=20) as resp:
            body = resp.read(200)
            must(resp.status == 200, "live main helper URL returns HTTP 200", fails)
            must(b"repair" in body.lower() or b"Otacon" in body or b"param" in body,
                 "live helper body looks like PowerShell", fails)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"live fetch failed: {exc}")
        print(f"FAIL  live fetch failed: {exc}")

    # 404 form must not be used
    bad = f"{repo}/{rel}"
    must(bad not in assistant or "Get-OtaconRawFileUrl" in assistant,
         "assistant does not construct branchless raw URL for repair", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Raw URL / repair helper regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
