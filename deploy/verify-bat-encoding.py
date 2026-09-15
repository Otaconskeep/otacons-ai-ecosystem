#!/usr/bin/env python3
"""Verify Windows .bat installers are UTF-8 BOM + CRLF with ASCII bodies."""
from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
ROOT = Path(__file__).resolve().parents[1]
CRLF = b"\r\n"


def check(path: Path) -> list[str]:
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


def main() -> int:
    bats = sorted(p for p in ROOT.rglob("*.bat") if ".git" not in p.parts)
    if not bats:
        print("no .bat files found", file=sys.stderr)
        return 2
    bad: list[str] = []
    for path in bats:
        errs = check(path)
        data = path.read_bytes()
        status = "FAIL" if errs else "OK"
        print(
            f"{status} {path.relative_to(ROOT)} "
            f"first3={data[:3].hex()} crlf={data.count(CRLF)} size={len(data)}"
        )
        bad.extend(errs)
    if bad:
        print("---")
        for err in bad:
            print(err)
        return 1
    print("all windows bat files: UTF-8 BOM + CRLF + ASCII body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
