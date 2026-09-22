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
    "OtaconExpansion-Setup.bat",
    "Reinstall-Otacon.bat",
    "Fix-Otacon-GPU.bat",
    "install_otacon.sh",
    "install_otacon_expansion.sh",
    "release.json",  # excluded from files[] self-hash
    # installer-revision.txt is downloaded from branch tip (unhashed); Linux sync target.
    "deploy/bootstrap-fetch.ps1",
    "deploy/windows-setup-assistant.ps1",
    "deploy/repair-otacon-core.ps1",
    "deploy/install-otacon-expansion.ps1",
    "deploy/wsl-bash-file.ps1",
    "deploy/fix-otacon-gpu.ps1",
    "deploy/get-fix-codec.cmd",
    "deploy/find-ubuntu.ps1",
    "deploy/install-wake-task.ps1",
    "deploy/install-desktop-launcher.ps1",
    "deploy/otacon-launcher.ico",
    "deploy/wake-otacon.ps1",
    "deploy/keep-ubuntu-awake.ps1",
    "deploy/download-one.ps1",
    "deploy/tail-log.ps1",
    "deploy/check-bat-encoding.ps1",
]

INSTALLER_VERSION = "1.3.6"
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
    # `commit` is the git object used for commit-pinned raw downloads (exact bytes).
    # GitHub's raw CDN for branch names like "main" may normalize CRLF->LF; commit
    # URLs serve the blob unchanged. Always record HEAD here (not installer-revision).
    commit = git_head()
    app_rev = commit
    if write_rev:
        # Optional: --pin-revision=<sha> pins Linux app sync target separately.
        explicit = None
        for arg in sys.argv:
            if arg.startswith("--pin-revision=") and len(arg) > len("--pin-revision="):
                explicit = arg.split("=", 1)[1].strip()
        if explicit:
            app_rev = explicit
        (ROOT / "deploy" / "installer-revision.txt").write_text(app_rev + "\n", encoding="utf-8")
    elif (ROOT / "deploy" / "installer-revision.txt").is_file():
        app_rev = (ROOT / "deploy" / "installer-revision.txt").read_text(encoding="utf-8").strip() or commit

    # Finalize on-disk published bytes, then hash those exact bytes.
    dirty: list[str] = []
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
                f"ERROR {rel}: working-tree publish bytes differ from HEAD blob "
                f"(WT={digest[:12]} HEAD={sha256_bytes(blob)[:12]}). "
                f"Commit the finalized encoding BEFORE writing release.json, or GitHub raw "
                f"will fail Windows sha256 checks (OTACON_FETCH_FAILED).",
                file=sys.stderr,
            )
            dirty.append(rel)
        files_meta.append({"path": rel, "sha256": digest, "bytes": len(data)})

    if dirty and "--allow-dirty-hash" not in sys.argv:
        print(
            f"REFUSING to write lying release.json ({len(dirty)} file(s) dirty). "
            f"Commit encoded installer bytes first, then re-run.",
            file=sys.stderr,
        )
        return 2

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
            "Each sha256 is the exact git blob / commit-pinned raw.githubusercontent.com bytes. "
            "Downloader verifies those raw bytes before any local normalization. "
            "Do not use branch-name raw URLs for hashed files (GitHub may normalize EOL on 'main')."
        ),
        "rule": "Installer-owned files are valid only when they match this release commit/hash. Existence alone is never enough.",
        "installer_revision": app_rev,
        "files": files_meta,
        "notes": (
            "Windows Setup always refreshes bootstrap-fetch.ps1, then refreshes this bundle "
            "from commit-pinned raw URLs. Pin ecosystem_ref to a tag/commit for production cutovers."
        ),
    }

    out = ROOT / "release.json"
    text = json.dumps(doc, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} installer_version={INSTALLER_VERSION} commit={commit} files={len(files_meta)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
