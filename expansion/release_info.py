"""Expansion release / install identity — pin vs tip clarity."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ['git', '-C', str(_repo_root()), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return ''


def release_identity() -> dict[str, Any]:
    """Explain soft-update pin vs git tip so users are not confused by two SHAs.

    Soft-update resets the working tree to ``release.json.commit`` (feature pin).
    ``origin/main`` tip may be a later ``chore(release)`` that only refreshes that pin.
    """
    root = _repo_root()
    release_path = root / 'release.json'
    release: dict[str, Any] = {}
    if release_path.is_file():
        try:
            release = json.loads(release_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            release = {}
    pin = str(release.get('commit') or '').strip()
    head = _git('rev-parse', 'HEAD')
    head_short = head[:7] if head else ''
    pin_short = pin[:7] if pin else ''
    origin_tip = _git('rev-parse', 'origin/main')
    origin_short = origin_tip[:7] if origin_tip else ''
    same = bool(pin and head and pin.startswith(head[: min(len(pin), len(head))]))
    # Also treat equal full hashes
    if pin and head and pin == head:
        same = True
    return {
        'product': release.get('product') or 'Otacon',
        'installer_version': release.get('installer_version') or '',
        'channel': release.get('channel') or 'public',
        'release_pin': pin,
        'release_pin_short': pin_short,
        'repo_head': head,
        'repo_head_short': head_short,
        'origin_main_tip': origin_tip,
        'origin_main_tip_short': origin_short,
        'matches_pin': same,
        'detail': (
            f'Installed feature pin {pin_short or "unknown"}'
            + (f' (repo HEAD {head_short})' if head_short and head_short != pin_short else '')
            + (
                f'; origin/main tip {origin_short} may be a later chore(release)'
                if origin_short and origin_short != pin_short
                else ''
            )
            + '. Soft-update follows release.json.commit (feature pin), not necessarily '
              'the latest chore(release) tip on origin/main.'
        ),
    }
