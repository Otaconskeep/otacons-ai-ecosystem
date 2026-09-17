"""Expansion user-state backup and restore.

Backup contains user-owned state only — never plaintext protected product
code, dossiers from the release bundle, or signing keys.
"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import EXPANSION_VERSION, current_versions

USER_TREES = (
    'user_emotions',
    'user_relationships',
    'user_memory',
    'user_journals',
    'user_diaries',
    'user_living_dossiers',
    'user_jobs',
    'user_events',
    'user_agents',
    'user_preferences',
    'user_pages',
)


@dataclass
class BackupReport:
    ok: bool
    path: str = ''
    members: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def create_backup(
    dest: Path,
    layout: Optional[StateLayout] = None,
) -> BackupReport:
    layout = layout or resolve_layout()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    members = []
    errors = []
    meta = {
        'created_at': time.time(),
        'expansion_version': EXPANSION_VERSION,
        'versions': current_versions().to_dict(),
        'kind': 'expansion_user_backup_v1',
        'note': 'User-owned state only. No protected product plaintext.',
    }
    try:
        with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('BACKUP.json', json.dumps(meta, indent=2) + '\n')
            members.append('BACKUP.json')
            for attr in USER_TREES:
                root = getattr(layout, attr)
                if not root.exists():
                    continue
                for path in root.rglob('*'):
                    if not path.is_file():
                        continue
                    # Never backup secrets/keys
                    if path.suffix == '.key' or 'secrets' in path.parts:
                        continue
                    arc = f'{attr}/{path.relative_to(root).as_posix()}'
                    zf.write(path, arcname=arc)
                    members.append(arc)
    except OSError as exc:
        return BackupReport(ok=False, path=str(dest), errors=[str(exc)])
    return BackupReport(ok=True, path=str(dest), members=members)


def restore_backup(
    archive: Path,
    layout: Optional[StateLayout] = None,
    *,
    overwrite: bool = True,
) -> BackupReport:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    archive = Path(archive)
    members = []
    errors = []
    try:
        with zipfile.ZipFile(archive, 'r') as zf:
            names = zf.namelist()
            if 'BACKUP.json' not in names:
                return BackupReport(ok=False, errors=['missing BACKUP.json'])
            meta = json.loads(zf.read('BACKUP.json'))
            if meta.get('kind') != 'expansion_user_backup_v1':
                return BackupReport(ok=False, errors=['unsupported backup kind'])
            for name in names:
                if name == 'BACKUP.json' or name.endswith('/'):
                    continue
                tree, _, rel = name.partition('/')
                if tree not in USER_TREES or not rel:
                    errors.append(f'skipped unexpected member {name}')
                    continue
                target_root = getattr(layout, tree)
                out = target_root / rel
                if out.exists() and not overwrite:
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(zf.read(name))
                members.append(name)
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return BackupReport(ok=False, errors=[str(exc)])
    return BackupReport(ok=not errors, path=str(archive), members=members, errors=errors)
