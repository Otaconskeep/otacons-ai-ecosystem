#!/usr/bin/env python3
"""Verify Windows packaging encoding by extension.

*.bat / *.cmd:
  UTF-8/ASCII WITHOUT BOM, CRLF, no UTF-16

deploy/*.ps1:
  UTF-8 WITH BOM, CRLF, ASCII body (PowerShell 5.1-safe)

Also verifies release.json SHA256 entries match the exact on-disk published bytes
(the same bytes GitHub raw will serve once committed as binary).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
ROOT = Path(__file__).resolve().parents[1]
CRLF = b"\r\n"
DEPLOY = ROOT / "deploy"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_bat(path: Path) -> list[str]:
    errs: list[str] = []
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        errs.append(f"{path}: UTF-16 is not allowed")
        return errs
    if data.startswith(BOM):
        errs.append(f"{path}: UTF-8 BOM is not allowed in .bat (breaks @echo off)")
    if data.count(b"\n") == 0:
        errs.append(f"{path}: no newlines")
    elif data.count(CRLF) != data.count(b"\n"):
        errs.append(f"{path}: mixed or LF-only line endings (need CRLF)")
    if any(byte >= 128 for byte in data):
        errs.append(f"{path}: non-ASCII bytes present (keep installer bats ASCII, no BOM)")
    return errs


def check_ps1(path: Path) -> list[str]:
    errs: list[str] = []
    data = path.read_bytes()
    if not data.startswith(BOM):
        errs.append(f"{path}: missing UTF-8 BOM (PS 5.1 requires BOM for UTF-8)")
    body = data[3:] if data.startswith(BOM) else data
    if body.count(b"\n") == 0:
        errs.append(f"{path}: no newlines")
    elif body.count(CRLF) != body.count(b"\n"):
        errs.append(f"{path}: mixed or LF-only line endings (need CRLF in published bytes)")
    if any(byte >= 128 for byte in body):
        errs.append(f"{path}: non-ASCII bytes present (keep deploy PS1 ASCII + BOM)")
    return errs


def check_release_manifest() -> list[str]:
    errs: list[str] = []
    rel_path = ROOT / "release.json"
    if not rel_path.is_file():
        return [f"{rel_path}: missing"]
    doc = json.loads(rel_path.read_text(encoding="utf-8"))
    files = doc.get("files") or []
    if not files:
        errs.append("release.json: empty files list")
    for entry in files:
        rel = entry.get("path")
        expect = (entry.get("sha256") or "").lower()
        if not rel or not expect:
            errs.append(f"release.json: incomplete entry {entry!r}")
            continue
        path = ROOT / rel
        if not path.is_file():
            errs.append(f"release.json: missing {rel}")
            continue
        data = path.read_bytes()
        got = sha256_bytes(data)
        if got != expect:
            errs.append(
                f"release.json hash mismatch for {rel}: "
                f"manifest={expect[:12]}... published={got[:12]}... "
                f"(hashes must be exact published/download bytes)"
            )
    return errs


def main() -> int:
    bats = sorted(
        p for p in ROOT.rglob("*.bat")
        if ".git" not in p.parts and "node_modules" not in p.parts
    )
    cmds = sorted(
        p for p in ROOT.rglob("*.cmd")
        if ".git" not in p.parts and "node_modules" not in p.parts
    )
    ps1s = sorted(DEPLOY.glob("*.ps1")) if DEPLOY.is_dir() else []
    if not bats:
        print("no .bat files found", file=sys.stderr)
        return 2
    bad: list[str] = []
    for path in bats + cmds:
        errs = check_bat(path)
        data = path.read_bytes()
        status = "FAIL" if errs else "OK"
        print(
            f"{status} {path.relative_to(ROOT)} "
            f"first3={data[:3].hex()} crlf={data.count(CRLF)} bom={data.startswith(BOM)} size={len(data)}"
        )
        bad.extend(errs)
    for path in ps1s:
        errs = check_ps1(path)
        data = path.read_bytes()
        status = "FAIL" if errs else "OK"
        print(
            f"{status} {path.relative_to(ROOT)} "
            f"first3={data[:3].hex()} crlf={data.count(CRLF)} size={len(data)}"
        )
        bad.extend(errs)
    for err in check_release_manifest():
        print(f"FAIL {err}")
        bad.append(err)
    if bad:
        print("---")
        for err in bad:
            print(err)
        return 1
    print("packaging OK: bats no-BOM+CRLF; deploy ps1 BOM+CRLF; release hashes match published bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
