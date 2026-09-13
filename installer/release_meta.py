"""Release pin metadata for reproducible public installs.

Development installs may still follow `main`. Public installers should prefer
OTACON_RELEASE / release.json when present.
"""
from __future__ import annotations

import json
from pathlib import Path

RELEASE = {
    'product': 'Otacon',
    'version': '0.1.0',
    'channel': 'public',
    'ecosystem_ref': 'main',  # replaced by tag when cutting a release
    'genome_voice_trainer_ref': 'main',
    'ai9_ref': 'main',
    'python_requires': '>=3.10,<3.14',
    'python_preferred': '3.12',
    'supported_os': [
        {'id': 'ubuntu', 'versions': ['22.04', '24.04'], 'support': 'supported'},
        {'id': 'debian', 'versions': ['12'], 'support': 'supported'},
        {'id': 'linuxmint', 'versions': ['21', '22'], 'support': 'best_effort'},
        {'id': 'pop', 'versions': ['22.04', '24.04'], 'support': 'best_effort'},
    ],
    'unsupported_os_notes': [
        'Ubuntu older than 22.04 is unsupported for native Tauri/WebKit builds.',
        'Core web-only install (OTACON_BUILD_NATIVE=0) may still work on best-effort distros.',
    ],
    'sha256': {
        # Filled when release artifacts are published. Empty means skip verify.
    },
}


def release_path() -> Path:
    return Path(__file__).resolve().parent.parent / 'release.json'


def load_release() -> dict:
    path = release_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            merged = dict(RELEASE)
            merged.update(data)
            return merged
        except (OSError, json.JSONDecodeError):
            pass
    return dict(RELEASE)


def write_default_release(path: Path | None = None) -> Path:
    target = path or release_path()
    target.write_text(json.dumps(RELEASE, indent=2) + '\n', encoding='utf-8')
    return target
