"""Expansion release / install identity — tip is the soft-update truth."""
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
    """Soft-update tracks origin/main tip. release.json.commit is provenance only."""
    root = _repo_root()
    release_path = root / 'release.json'
    release: dict[str, Any] = {}
    if release_path.is_file():
        try:
            release = json.loads(release_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            release = {}
    recorded = str(release.get('commit') or '').strip()
    head = _git('rev-parse', 'HEAD')
    head_short = head[:7] if head else ''
    recorded_short = recorded[:7] if recorded else ''
    origin_tip = _git('rev-parse', 'origin/main')
    origin_short = origin_tip[:7] if origin_tip else ''
    matches_tip = bool(
        head and origin_tip and (head == origin_tip or head.startswith(origin_tip[:12]))
    )
    return {
        'product': release.get('product') or 'Otacon',
        'installer_version': release.get('installer_version') or '',
        'channel': release.get('channel') or 'public',
        'release_pin': recorded,
        'release_pin_short': recorded_short,
        'repo_head': head,
        'repo_head_short': head_short,
        'origin_main_tip': origin_tip,
        'origin_main_tip_short': origin_short,
        'matches_pin': matches_tip,
        'soft_update_target': 'origin/main',
        'detail': (
            f'Soft-update tracks origin/main tip ({origin_short or head_short or "unknown"}). '
            f'release.json.commit={recorded_short or "unset"} is provenance only — '
            f'not an archived install checkout.'
        ),
    }
