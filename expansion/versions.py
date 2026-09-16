"""Independent version tracks for Core, Expansion, and persisted schemas.

Update architecture requires these to move independently. Schema versions
key migrations; package versions key signed manifests and rollbacks.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from expansion.schema import AGENT_SCHEMA_VERSION
from expansion.state_layout import resolve_layout

# Product package version (Expansion layer). Bump on Expansion releases.
EXPANSION_VERSION = '0.1.0-foundation'

# Persisted-shape versions — bump when on-disk formats change meaning.
DOSSIER_SCHEMA_VERSION = 1
RELATIONSHIP_SCHEMA_VERSION = 1
EMOTION_SCHEMA_VERSION = 1
MEMORY_SCHEMA_VERSION = 1
EVENT_SCHEMA_VERSION = 1
TOPOLOGY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
MIGRATION_ENGINE_VERSION = 1


@dataclass(frozen=True)
class VersionSet:
    core_version: str
    expansion_version: str
    agent_schema: int
    dossier_schema: int
    relationship_schema: int
    emotion_schema: int
    memory_schema: int
    event_schema: int
    topology_schema: int
    manifest_schema: int
    migration_engine: int

    def to_dict(self) -> dict:
        return asdict(self)


def read_core_version(install_dir: Optional[Path] = None) -> str:
    """Best-effort Core version from release.json; unknown if absent."""
    import os
    root = Path(
        install_dir
        or os.environ.get('OTACON_INSTALL_DIR', Path.home() / 'otacon-ai-ecosystem')
    ).expanduser()
    release = root / 'release.json'
    if release.is_file():
        try:
            data = json.loads(release.read_text(encoding='utf-8'))
            return str(data.get('version') or 'unknown')
        except (json.JSONDecodeError, OSError):
            return 'unknown'
    # When running from the repo checkout that contains this module:
    here = Path(__file__).resolve().parents[1] / 'release.json'
    if here.is_file():
        try:
            data = json.loads(here.read_text(encoding='utf-8'))
            return str(data.get('version') or 'unknown')
        except (json.JSONDecodeError, OSError):
            return 'unknown'
    return 'unknown'


def current_versions(install_dir: Optional[Path] = None) -> VersionSet:
    return VersionSet(
        core_version=read_core_version(install_dir),
        expansion_version=EXPANSION_VERSION,
        agent_schema=AGENT_SCHEMA_VERSION,
        dossier_schema=DOSSIER_SCHEMA_VERSION,
        relationship_schema=RELATIONSHIP_SCHEMA_VERSION,
        emotion_schema=EMOTION_SCHEMA_VERSION,
        memory_schema=MEMORY_SCHEMA_VERSION,
        event_schema=EVENT_SCHEMA_VERSION,
        topology_schema=TOPOLOGY_SCHEMA_VERSION,
        manifest_schema=MANIFEST_SCHEMA_VERSION,
        migration_engine=MIGRATION_ENGINE_VERSION,
    )


def versions_path(layout=None) -> Path:
    layout = layout or resolve_layout()
    return layout.user_config_root / 'versions.json'


def save_installed_versions(versions: Optional[VersionSet] = None, path: Optional[Path] = None) -> Path:
    versions = versions or current_versions()
    path = path or versions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(versions.to_dict(), indent=2) + '\n', encoding='utf-8')
    return path


def load_installed_versions(path: Optional[Path] = None) -> Optional[VersionSet]:
    path = path or versions_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    return VersionSet(**{k: data[k] for k in VersionSet.__dataclass_fields__ if k in data})
