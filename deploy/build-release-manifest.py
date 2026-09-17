#!/usr/bin/env python3
"""Build release.json from FINAL published artifact bytes.

Canonical rule:
  SHA256(manifest) == SHA256(exact bytes served by GitHub raw / downloaded by Setup)

Never hash a post-normalization representation that differs from the published blob.
Optional local normalization may happen ONLY AFTER download verification.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUNDLE_FILES = [
    "install_otacon.bat",
    "OtaconsKeep-Setup.bat",
    "Reinstall-Otacon.bat",
    "Fix-Otacon-GPU.bat",
    "install_otacon.sh",
    "release.json",  # excluded from files[] self-hash
    "deploy/installer-revision.txt",
    "deploy/bootstrap-fetch.ps1",
    "deploy/windows-setup-assistant.ps1",
    "deploy/repair-otacon-core.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/fix-otacon-gpu.ps1",
    "deploy/get-fix-codec.cmd",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/wake-otacon.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1",
]

INSTALLER_VERSION = "1.1.1"
BOM = b"\xef\xbb\xbf"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        rev = (ROOT / "deploy" / "installer-revision.txt").read_text(encoding="utf-8").strip()
        return rev or "unknown"


def git_blob_bytes(rel: str) -> bytes | None:
    """Return committed blob bytes for rel (what GitHub raw serves), if present."""
    try:
        return subprocess.check_output(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT
        )
    except subprocess.CalledProcessError:
        return None


def ensure_published_encoding(rel: str, path: Path) -> None:
    """Apply final packaging transforms BEFORE hashing (in place)."""
    data = path.read_bytes()
    if rel.endswith(".bat") or rel.endswith(".cmd"):
        if data.startswith(BOM):
            data = data[3:]
        text = data.decode("utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if any(ord(c) > 127 for c in text):
            raise SystemExit(f"{rel}: non-ASCII content not allowed in bat/cmd")
        out = text.replace("\n", "\r\n").encode("ascii")
        if not out.endswith(b"\r\n"):
            out += b"\r\n"
        path.write_bytes(out)
        return
    if rel.endswith(".ps1"):
        if data.startswith(BOM):
            body = data[3:]
        else:
            body = data
        text = body.decode("utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if any(ord(c) > 127 for c in text):
            # Keep ASCII for PS 5.1 safety in installer helpers.
            raise SystemExit(f"{rel}: non-ASCII content not allowed in deploy ps1 helpers")
        out = BOM + text.replace("\n", "\r\n").encode("ascii")
        if not out.endswith(b"\r\n"):
            out += b"\r\n"
        path.write_bytes(out)


def main() -> int:
    write_rev = "--pin-revision" in sys.argv
    commit = git_head()
    if write_rev:
        (ROOT / "deploy" / "installer-revision.txt").write_text(commit + "\n", encoding="utf-8")
    else:
        rev_path = ROOT / "deploy" / "installer-revision.txt"
        if rev_path.is_file():
            pinned = rev_path.read_text(encoding="utf-8").strip()
            if pinned:
                commit = pinned

    # Finalize on-disk published bytes, then hash those exact bytes.
    for rel in BUNDLE_FILES:
        if rel == "release.json":
            continue
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            return 1
        if rel.endswith((".bat", ".cmd", ".ps1")):
            ensure_published_encoding(rel, path)

    files_meta = []
    for rel in BUNDLE_FILES:
        if rel == "release.json":
            continue
        path = ROOT / rel
        data = path.read_bytes()
        digest = sha256_bytes(data)
        # Warn if HEAD blob already differs (would mean previous commit != working tree publish form).
        blob = git_blob_bytes(rel)
        if blob is not None and sha256_bytes(blob) != digest:
            print(
                f"WARN {rel}: working-tree publish bytes differ from HEAD blob "
                f"(commit the finalized bytes so GitHub raw matches the manifest)",
                file=sys.stderr,
            )
        files_meta.append({"path": rel, "sha256": digest, "bytes": len(data)})

    doc = {
        "product": "Otacon",
        "installer_version": INSTALLER_VERSION,
        "commit": commit,
        "channel": "public",
        "ecosystem_ref": "main",
        "genome_voice_trainer_ref": "main",
        "ai9_ref": "main",
        "python_requires": ">=3.10,<3.14",
        "python_preferred": "3.12",
        "hash_rule": (
            "Each sha256 is the exact published/download bytes (GitHub raw). "
            "Downloader verifies raw bytes before any local normalization."
        ),
        "rule": "Installer-owned files are valid only when they match this release commit/hash. Existence alone is never enough.",
        "files": files_meta,
        "notes": (
            "Windows Setup always refreshes bootstrap-fetch.ps1, then refreshes this bundle. "
            "Pin ecosystem_ref to a tag/commit for production cutovers."
        ),
    }

    out = ROOT / "release.json"
    text = json.dumps(doc, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} installer_version={INSTALLER_VERSION} commit={commit} files={len(files_meta)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
