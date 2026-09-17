#!/usr/bin/env python3
"""Build release.json installer bundle metadata (version + commit + SHA256)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Installer-owned files that must match GitHub on every Setup launch.
BUNDLE_FILES = [
    "install_otacon.bat",
    "OtaconsKeep-Setup.bat",
    "Reinstall-Otacon.bat",
    "Fix-Otacon-GPU.bat",
    "install_otacon.sh",
    "release.json",  # placeholder; hashed after write without self
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

INSTALLER_VERSION = "1.1.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        rev = (ROOT / "deploy" / "installer-revision.txt").read_text(encoding="utf-8").strip()
        return rev or "unknown"


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


    files_meta = []
    for rel in BUNDLE_FILES:
        if rel == "release.json":
            continue
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            return 1
        files_meta.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})

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
    # Re-hash release.json itself is optional; bootstrap verifies listed files.
    print(f"wrote {out} installer_version={INSTALLER_VERSION} commit={commit} files={len(files_meta)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
