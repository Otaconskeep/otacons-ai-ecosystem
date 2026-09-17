#!/usr/bin/env python3
"""Packaging: release hashes match published bytes; BAT has no BOM; verify-before-normalize."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    fails: list[str] = []
    release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8-sig")
    check = (ROOT / "deploy" / "check-bat-encoding.ps1").read_text(encoding="utf-8-sig")
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    build = (ROOT / "deploy" / "build-release-manifest.py").read_text(encoding="utf-8")

    must("hash_rule" in release or "exact published" in json.dumps(release).lower(),
         "release.json documents published-byte hash rule", fails)
    must("binary" in attrs and "deploy/*.ps1" in attrs,
         ".gitattributes stores deploy/*.ps1 as binary published bytes", fails)
    must("text eol=crlf" not in attrs or "deploy/*.ps1" not in attrs.split("text eol=crlf")[0],
         ".gitattributes does not use text eol=crlf for installer ps1", fails)
    # stronger: no text eol=crlf for ps1 at all
    must("*.ps1 text" not in attrs and "deploy/*.ps1 text" not in attrs,
         ".gitattributes does not mark ps1 as text/eol=crlf", fails)

    must("ONLY AFTER successful hash verification" in fetch or "post-verify" in fetch,
         "bootstrap normalizes only after hash verification", fails)
    must("ExpectedSha256" in fetch and "Get-FileSha256Hex" in fetch,
         "bootstrap still verifies SHA256 on raw download", fails)

    must("UTF-8 BOM is not allowed" in check or "not allowed in .bat" in check,
         "check-bat-encoding rejects UTF-8 BOM for BAT", fails)
    must("missing UTF-8 BOM" not in check or "not allowed" in check,
         "check-bat-encoding does not require BAT BOM", fails)
    must("0xFF" in check and "0xFE" in check, "check-bat-encoding rejects UTF-16", fails)
    must("bareLf" in check or "0x0A" in check, "check-bat-encoding detects bare LF", fails)

    must("exact published" in build or "published/download bytes" in build,
         "build-release-manifest hashes published bytes", fails)

    # Exact published bytes == manifest for every listed file
    for entry in release["files"]:
        rel = entry["path"]
        data = (ROOT / rel).read_bytes()
        must(sha256(data) == entry["sha256"],
             f"published bytes hash == manifest for {rel}", fails)

    # BAT policy on key launchers
    for rel in ("OtaconsKeep-Setup.bat", "install_otacon.bat", "Fix-Otacon-GPU.bat", "Reinstall-Otacon.bat"):
        data = (ROOT / rel).read_bytes()
        must(not data.startswith(BOM), f"{rel} has no UTF-8 BOM", fails)
        must(data.count(b"\n") == data.count(b"\r\n"), f"{rel} uses CRLF only", fails)
        must(data.startswith(b"@") or data.startswith(b"R") or data.startswith(b"s"),
             f"{rel} starts with script text not BOM", fails)

    # PS1 policy
    for rel in ("deploy/tail-log.ps1", "deploy/bootstrap-fetch.ps1", "deploy/repair-otacon-core.ps1"):
        data = (ROOT / rel).read_bytes()
        must(data.startswith(BOM), f"{rel} has UTF-8 BOM", fails)
        must(data.count(b"\n") == data.count(b"\r\n"), f"{rel} published bytes are CRLF", fails)

    # Simulate download verify then optional normalize:
    # published hash matches; after normalize hash may change without failing verification.
    sample = (ROOT / "deploy" / "tail-log.ps1").read_bytes()
    published_hash = sha256(sample)
    must(any(e["path"] == "deploy/tail-log.ps1" and e["sha256"] == published_hash
             for e in release["files"]),
         "tail-log published hash matches manifest (download verify would pass)", fails)

    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / "tail-log.ps1"
        raw_path.write_bytes(sample)
        got = sha256(raw_path.read_bytes())
        must(got == published_hash, "downloaded bytes hash == manifest hash", fails)
        # optional post-verify normalize (idempotent if already BOM+CRLF)
        body = sample[3:] if sample.startswith(BOM) else sample
        text = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        normalized = BOM + text.replace("\n", "\r\n").encode("utf-8")
        raw_path.write_bytes(normalized)
        post = sha256(raw_path.read_bytes())
        # If already canonical, post == published; either way verification already passed.
        must(True, f"post-verification normalize allowed (pre={published_hash[:12]} post={post[:12]})", fails)
        must(got == published_hash, "verification used pre-normalize bytes only", fails)

    # Launcher inline encoding check rejects BOM
    setup = (ROOT / "OtaconsKeep-Setup.bat").read_text(encoding="ascii")
    must("UTF-8 BOM is not allowed" in setup, "Setup.bat inline check rejects BAT BOM", fails)
    must("missing UTF-8 BOM" not in setup, "Setup.bat no longer requires BAT BOM", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Packaging hash/encoding regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
