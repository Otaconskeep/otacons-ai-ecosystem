"""Uninstall Expansion product vs purge Expansion user data.

UNINSTALL: remove product/runtime; preserve user state.
PURGE: requires explicit confirmation; removes Expansion user data.
Never conflate the two.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout

PURGE_CONFIRMATION = 'PURGE_EXPANSION_USER_DATA'


@dataclass
class UninstallReport:
    ok: bool
    mode: str  # uninstall | purge
    removed: list = field(default_factory=list)
    preserved: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def uninstall_expansion(layout: Optional[StateLayout] = None) -> UninstallReport:
    """Remove staged packages / product pointers; keep user state."""
    layout = layout or resolve_layout()
    removed = []
    preserved = []
    errors = []
    # Remove package versions (product), keep user_* trees
    pkg_root = layout.package_versions_root
    if pkg_root.exists():
        try:
            shutil.rmtree(pkg_root)
            removed.append(str(pkg_root))
            pkg_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(str(exc))
    for label, path in (
        ('emotions', layout.user_emotions),
        ('relationships', layout.user_relationships),
        ('memory', layout.user_memory),
        ('journals', layout.user_journals),
        ('diaries', layout.user_diaries),
        ('living_dossiers', layout.user_living_dossiers),
        ('jobs', layout.user_jobs),
        ('preferences', layout.user_preferences),
        ('agents', layout.user_agents),
    ):
        if path.exists():
            preserved.append(label)
    # Mark uninstall
    marker = layout.user_config_root / 'UNINSTALLED.json'
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({
        'mode': 'uninstall',
        'preserved': preserved,
        'note': 'User Expansion state preserved. Reinstall will restore the owner Keep.',
    }, indent=2) + '\n', encoding='utf-8')
    return UninstallReport(ok=not errors, mode='uninstall', removed=removed, preserved=preserved, errors=errors)


def purge_expansion_user_data(
    layout: Optional[StateLayout] = None,
    *,
    confirmation: str,
) -> UninstallReport:
    """Explicitly destroy Expansion user data. Requires exact confirmation string."""
    if confirmation != PURGE_CONFIRMATION:
        return UninstallReport(
            ok=False, mode='purge',
            errors=[f'confirmation required: {PURGE_CONFIRMATION!r}'],
        )
    layout = layout or resolve_layout()
    removed = []
    errors = []
    for path in (
        layout.user_emotions,
        layout.user_relationships,
        layout.user_memory,
        layout.user_journals,
        layout.user_diaries,
        layout.user_living_dossiers,
        layout.user_jobs,
        layout.user_events,
        layout.user_agents,
        layout.user_pages,
        layout.secrets_root,
    ):
        if path.exists():
            try:
                shutil.rmtree(path)
                removed.append(str(path))
            except OSError as exc:
                errors.append(str(exc))
    # preferences: remove expansion-specific but leave dir
    prefs = layout.user_preferences
    if prefs.is_dir():
        for child in prefs.iterdir():
            try:
                if child.is_file():
                    child.unlink()
                    removed.append(str(child))
                elif child.is_dir():
                    shutil.rmtree(child)
                    removed.append(str(child))
            except OSError as exc:
                errors.append(str(exc))
    return UninstallReport(ok=not errors, mode='purge', removed=removed, errors=errors)
