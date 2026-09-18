"""Secure local secrets for optional integrations (Discord, HA, …).

Never commit these files. Paths under ~/.config/otacon/secrets/ with mode 0600.
Installer/Expansion may create the directory; tokens come from the user only.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional


def secrets_dir() -> Path:
    override = (os.environ.get('OTACON_SECRETS_DIR') or '').strip()
    if override:
        d = Path(override)
    else:
        d = Path.home() / '.config' / 'otacon' / 'secrets'
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def secret_path(name: str) -> Path:
    safe = ''.join(c for c in (name or '') if c.isalnum() or c in ('-', '_', '.'))
    if not safe:
        raise ValueError('secret name required')
    return secrets_dir() / safe


def write_env_secret(name: str, mapping: dict[str, str]) -> Path:
    """Write KEY=value lines; file mode 0600. Values must not include newlines."""
    path = secret_path(name if name.endswith('.env') else f'{name}.env')
    lines = []
    for k, v in (mapping or {}).items():
        key = str(k).strip()
        if not key:
            continue
        val = str(v or '').replace('\n', '').replace('\r', '')
        lines.append(f'{key}={val}')
    path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def read_env_secret(name: str) -> dict[str, str]:
    path = secret_path(name if name.endswith('.env') else f'{name}.env')
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            out[k.strip()] = v
    except OSError:
        return {}
    return out


def has_secret_key(name: str, key: str) -> bool:
    return bool((read_env_secret(name).get(key) or '').strip())
