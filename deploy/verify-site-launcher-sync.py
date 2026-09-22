#!/usr/bin/env python3
"""Fail if the public site download bat drifts from release.json / tip.

Crist caught this twice (v1.3.9 cosmetic, v1.3.11 DEGRADED exit). Run after
bumping installer bats and after syncing Otaconskeep.github.io downloads/.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_CANDIDATES = [
    Path("/root/Otaconskeep.github.io/downloads"),
    Path("/root/otaconskeep-site/downloads"),
]
LIVE_URL = "https://otaconskeep.github.io/downloads/OtaconExpansion-Setup.bat"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    rel = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    tip = next(f for f in rel["files"] if f["path"] == "OtaconExpansion-Setup.bat")
    tip_path = ROOT / "OtaconExpansion-Setup.bat"
    tip_bytes = tip_path.read_bytes()
    tip_hash = sha256(tip_bytes)
    fails: list[str] = []

    if tip_hash != tip["sha256"] or len(tip_bytes) != tip["bytes"]:
        fails.append(
            f"repo bat hash/bytes mismatch release.json "
            f"(repo={tip_hash[:12]}/{len(tip_bytes)} release={tip['sha256'][:12]}/{tip['bytes']})"
        )

    for downloads in SITE_CANDIDATES:
        bat = downloads / "OtaconExpansion-Setup.bat"
        if not bat.is_file():
            continue
        site_bytes = bat.read_bytes()
        site_hash = sha256(site_bytes)
        if site_hash != tip_hash:
            fails.append(
                f"{bat}: stale vs tip "
                f"(site={site_hash[:12]}/{len(site_bytes)} tip={tip_hash[:12]}/{len(tip_bytes)})"
            )

    try:
        with urllib.request.urlopen(LIVE_URL, timeout=20) as resp:
            live = resp.read()
        live_hash = sha256(live)
        if live_hash != tip_hash:
            fails.append(
                f"LIVE {LIVE_URL}: stale vs tip "
                f"(live={live_hash[:12]}/{len(live)} tip={tip_hash[:12]}/{len(tip_bytes)})"
            )
        else:
            print(f"OK live site matches tip {tip_hash[:12]} ({len(tip_bytes)} bytes)")
    except Exception as exc:
        fails.append(f"LIVE fetch failed: {exc}")

    if fails:
        print("FAIL site launcher sync:", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK site launcher sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
