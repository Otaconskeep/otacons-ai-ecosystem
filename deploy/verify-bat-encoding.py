#!/usr/bin/env python3
"""Verify Windows .bat installers are UTF-8 BOM + CRLF with ASCII bodies.

Also gate deploy/*.ps1: UTF-8 BOM + ASCII body (LF OK). Windows PowerShell 5.1
reads scripts without a BOM as the system ANSI code page; UTF-8 em-dashes then
decode to a curly quote (0x94) that terminates strings -> instant parse exit 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
ROOT = Path(__file__).resolve().parents[1]
CRLF = b"\r\n"
DEPLOY = ROOT / "deploy"


def check_bat(path: Path) -> list[str]:
    errs: list[str] = []
    data = path.read_bytes()
    if not data.startswith(BOM):
        errs.append(f"{path}: missing UTF-8 BOM (need EF BB BF), first3={data[:3].hex()}")
    body = data[3:] if data.startswith(BOM) else data
    if body.count(b"\n") == 0:
        errs.append(f"{path}: no newlines")
    elif body.count(CRLF) != body.count(b"\n"):
        errs.append(f"{path}: mixed or LF-only line endings (need CRLF)")
    if any(byte >= 128 for byte in body):
        errs.append(f"{path}: non-ASCII bytes present (keep installer bats ASCII + BOM)")
    return errs


def check_ps1(path: Path) -> list[str]:
    errs: list[str] = []
    data = path.read_bytes()
    if not data.startswith(BOM):
        errs.append(f"{path}: missing UTF-8 BOM (PS 5.1 requires BOM for UTF-8)")
    body = data[3:] if data.startswith(BOM) else data
    if any(byte >= 128 for byte in body):
        errs.append(f"{path}: non-ASCII bytes present (keep deploy PS1 ASCII + BOM)")
    return errs


def main() -> int:
    bats = sorted(p for p in ROOT.rglob("*.bat") if ".git" not in p.parts)
    ps1s = sorted(DEPLOY.glob("*.ps1")) if DEPLOY.is_dir() else []
    if not bats:
        print("no .bat files found", file=sys.stderr)
        return 2
    bad: list[str] = []
    for path in bats:
        errs = check_bat(path)
        data = path.read_bytes()
        status = "FAIL" if errs else "OK"
        print(
            f"{status} {path.relative_to(ROOT)} "
            f"first3={data[:3].hex()} crlf={data.count(CRLF)} size={len(data)}"
        )
        bad.extend(errs)
    for path in ps1s:
        errs = check_ps1(path)
        data = path.read_bytes()
        status = "FAIL" if errs else "OK"
        print(
            f"{status} {path.relative_to(ROOT)} "
            f"first3={data[:3].hex()} size={len(data)}"
        )
        bad.extend(errs)
    if bad:
        print("---")
        for err in bad:
            print(err)
        return 1
    print("all windows bat files: UTF-8 BOM + CRLF + ASCII body")
    print("all deploy ps1 files: UTF-8 BOM + ASCII body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
