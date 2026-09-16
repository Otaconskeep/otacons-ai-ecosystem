"""Update / rollback for protected Expansion packages."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.migrations import apply_pending, snapshot_user_state
from expansion.protected.verify import verify_protected_package
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class UpdateResult:
    ok: bool
    action: str  # updated | rolled_back | rejected | noop
    from_version: str = ''
    to_version: str = ''
    errors: list = field(default_factory=list)
    snapshot: str = ''
    preserve_user_data: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def stage_package(package_dir: Path, layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.package_versions_root.mkdir(parents=True, exist_ok=True)
    dest = layout.package_versions_root / package_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(package_dir, dest)
    return dest


def switch_current(version_dir: Path, layout: Optional[StateLayout] = None) -> None:
    layout = layout or resolve_layout()
    layout.package_versions_root.mkdir(parents=True, exist_ok=True)
    meta = {
        'version': version_dir.name,
        'path': str(version_dir.resolve()),
        'switched_at': time.time(),
    }
    (layout.package_versions_root / 'current.json').write_text(
        json.dumps(meta, indent=2) + '\n', encoding='utf-8',
    )
    link = layout.package_versions_root / 'current'
    try:
        if link.is_symlink() or link.is_file():
            link.unlink()
        if not link.exists():
            link.symlink_to(version_dir.resolve(), target_is_directory=True)
    except OSError:
        pass


def apply_protected_update(
    new_package_dir: Path,
    *,
    layout: Optional[StateLayout] = None,
    public_key_pem: bytes,
    run_migrations: bool = True,
) -> UpdateResult:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()

    vr = verify_protected_package(new_package_dir, public_key_pem=public_key_pem)
    if not vr.ok:
        return UpdateResult(
            ok=False, action='rejected', errors=list(vr.errors),
            to_version=new_package_dir.name,
        )

    from_ver = ''
    cur_meta_path = layout.package_versions_root / 'current.json'
    if cur_meta_path.is_file():
        cur_meta = json.loads(cur_meta_path.read_text(encoding='utf-8'))
        from_ver = str(cur_meta.get('version') or '')
        shutil.copy2(cur_meta_path, layout.package_versions_root / 'previous.json')

    snap = snapshot_user_state(layout, label='pre-update')
    staged = stage_package(new_package_dir, layout)

    try:
        if run_migrations:
            apply_pending(layout)
        switch_current(staged, layout)
        vr2 = verify_protected_package(staged, public_key_pem=public_key_pem)
        if not vr2.ok:
            raise RuntimeError('; '.join(vr2.errors))
        return UpdateResult(
            ok=True, action='updated',
            from_version=from_ver, to_version=staged.name,
            snapshot=str(snap),
        )
    except Exception as exc:  # noqa: BLE001
        errors = [str(exc)]
        prev = layout.package_versions_root / 'previous.json'
        if prev.is_file():
            prev_meta = json.loads(prev.read_text(encoding='utf-8'))
            prev_path = Path(prev_meta.get('path') or '')
            if prev_path.is_dir():
                switch_current(prev_path, layout)
                return UpdateResult(
                    ok=False, action='rolled_back',
                    from_version=staged.name, to_version=prev_path.name,
                    errors=errors, snapshot=str(snap),
                )
        return UpdateResult(
            ok=False, action='rolled_back',
            errors=errors + ['no previous package to restore'],
            snapshot=str(snap),
        )


def rollback_to_previous(layout: Optional[StateLayout] = None) -> UpdateResult:
    layout = layout or resolve_layout()
    prev = layout.package_versions_root / 'previous.json'
    if not prev.is_file():
        return UpdateResult(ok=False, action='noop', errors=['no previous package'])
    meta = json.loads(prev.read_text(encoding='utf-8'))
    path = Path(meta['path'])
    if not path.is_dir():
        return UpdateResult(ok=False, action='noop', errors=['previous package missing on disk'])
    # Swap current -> becomes recoverable; set previous as current
    cur = layout.package_versions_root / 'current.json'
    if cur.is_file():
        shutil.copy2(cur, layout.package_versions_root / 'previous.json')
    switch_current(path, layout)
    return UpdateResult(ok=True, action='rolled_back', to_version=path.name)
