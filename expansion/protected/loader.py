"""Runtime loader for protected product resources.

Dev channel: load plaintext product/dossiers/*.json (canonical SoT).
Protected channel: decrypt protected-bundle.enc via KeyProvider.

Never returns raw package keys or signing private keys to callers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from expansion.dossier import CanonicalDossier, canonical_from_dict, validate_canonical_dossier
from expansion.protected.bundle import BUNDLE_NAME, decrypt_bundle_archive, extract_member
from expansion.protected.keys import KeyProvider, default_key_provider
from expansion.state_layout import StateLayout, resolve_layout

BUNDLE_KEY_NAME = 'expansion-bundle'


class ProtectedResourceLoader:
    def __init__(
        self,
        layout: Optional[StateLayout] = None,
        *,
        key_provider: Optional[KeyProvider] = None,
        channel: str = 'dev',
        package_dir: Optional[Path] = None,
    ):
        self.layout = layout or resolve_layout()
        self.keys = key_provider or default_key_provider(self.layout)
        self.channel = channel
        self.package_dir = package_dir or (self.layout.product_root / 'product')

    def load_canonical_dossier(self, agent_id: str) -> CanonicalDossier:
        if self.channel in ('dev', 'public'):
            from expansion.canonical_dossiers import get_canonical_dossier
            return get_canonical_dossier(agent_id, self.layout)
        wire_path = self.package_dir / BUNDLE_NAME
        if not wire_path.is_file():
            raise FileNotFoundError(f'protected bundle missing: {wire_path}')
        key = self.keys.load(BUNDLE_KEY_NAME)
        archive = decrypt_bundle_archive(wire_path.read_bytes(), key)
        raw = json.loads(extract_member(archive, f'dossiers/{agent_id}.json'))
        dossier = canonical_from_dict(raw)
        errors = validate_canonical_dossier(dossier)
        if errors:
            raise ValueError(f'{agent_id}: {errors}')
        return dossier

    def list_bundle_members(self) -> list[str]:
        if self.channel in ('dev', 'public'):
            root = self.layout.product_root / 'product' / 'dossiers'
            return sorted(p.name for p in root.glob('*.json'))
        wire_path = self.package_dir / BUNDLE_NAME
        key = self.keys.load(BUNDLE_KEY_NAME)
        archive = decrypt_bundle_archive(wire_path.read_bytes(), key)
        import io, tarfile
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            return [m.name for m in tar.getmembers() if m.isfile()]
