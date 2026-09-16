"""Protected product bundle — encrypts canonical product resources.

Includes (product only — never user state):
  canonical dossiers, system prompts/persona resources, relationship presets,
  emotion configuration, premium workflow definitions, private templates,
  protected assets where appropriate.

Dev JSON under product/dossiers remains SoT for development.
Release build: validate → package → encrypt → protected-bundle.enc
"""
from __future__ import annotations

import io
import json
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from expansion.canonical_dossiers import CANONICAL_AGENT_IDS, list_product_dossier_paths
from expansion.protected.aead import (
    AEAD_AES_256_GCM,
    EncryptedBlob,
    decrypt_aes_gcm,
    encrypt_aes_gcm,
    generate_bundle_key,
)
from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import EXPANSION_VERSION

BUNDLE_NAME = 'protected-bundle.enc'
BUNDLE_META_NAME = 'protected-bundle.meta.json'


@dataclass
class BundleBuildResult:
    bundle_path: Path
    meta_path: Path
    key: bytes
    aead: str
    member_names: list
    sha256: str


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def collect_product_members(layout: Optional[StateLayout] = None) -> list[tuple[str, bytes]]:
    """Gather product-only files for the protected archive."""
    layout = layout or resolve_layout()
    members: list[tuple[str, bytes]] = []
    # Canonical dossiers (dev SoT → release encrypted)
    for path in list_product_dossier_paths(layout):
        members.append((f'dossiers/{path.name}', path.read_bytes()))
    # Relationship / emotion seed presets if present
    presets = layout.product_root / 'product' / 'presets'
    if presets.is_dir():
        for path in sorted(presets.rglob('*')):
            if path.is_file():
                rel = path.relative_to(layout.product_root / 'product')
                members.append((str(rel).replace('\\', '/'), path.read_bytes()))
    # Persona/system prompt resources (product only)
    prompts = layout.product_root / 'product' / 'prompts'
    if prompts.is_dir():
        for path in sorted(prompts.rglob('*.txt')) + sorted(prompts.rglob('*.json')):
            if path.is_file():
                rel = path.relative_to(layout.product_root / 'product')
                members.append((str(rel).replace('\\', '/'), path.read_bytes()))
    # Minimal emotion config stamp
    emotion_cfg = {
        'schema': 'emotion_config_v1',
        'note': 'Baselines live on canonical dossiers; this stamps package identity.',
        'expansion_version': EXPANSION_VERSION,
        'agents': list(CANONICAL_AGENT_IDS),
    }
    members.append(('config/emotion.json', json.dumps(emotion_cfg, indent=2).encode()))
    return members


def build_plaintext_archive(members: Iterable[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, data in members:
            _add_bytes(tar, name, data)
    return buf.getvalue()


def encrypt_bundle(
    plaintext_archive: bytes,
    key: Optional[bytes] = None,
    *,
    aad: bytes = b'otacon-expansion-protected-v1',
) -> tuple[EncryptedBlob, bytes]:
    key = key or generate_bundle_key()
    blob = encrypt_aes_gcm(plaintext_archive, key, aad=aad)
    return blob, key


def write_protected_bundle(
    out_dir: Path,
    layout: Optional[StateLayout] = None,
    *,
    key: Optional[bytes] = None,
) -> BundleBuildResult:
    import hashlib
    layout = layout or resolve_layout()
    members = collect_product_members(layout)
    if not members:
        raise ValueError('no product members to protect')
    archive = build_plaintext_archive(members)
    blob, key = encrypt_bundle(archive, key=key)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / BUNDLE_NAME
    wire = blob.to_wire()
    bundle_path.write_bytes(wire)
    meta = {
        'aead': blob.aead,
        'aad': 'otacon-expansion-protected-v1',
        'member_count': len(members),
        'members': [n for n, _ in members],
        'expansion_version': EXPANSION_VERSION,
        'created_at': time.time(),
        # never store key here
    }
    meta_path = out_dir / BUNDLE_META_NAME
    meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    digest = hashlib.sha256(wire).hexdigest()
    return BundleBuildResult(
        bundle_path=bundle_path,
        meta_path=meta_path,
        key=key,
        aead=AEAD_AES_256_GCM,
        member_names=[n for n, _ in members],
        sha256=digest,
    )


def decrypt_bundle_archive(wire: bytes, key: bytes) -> bytes:
    blob = EncryptedBlob.from_wire(wire)
    return decrypt_aes_gcm(blob, key)


def extract_member(archive_bytes: bytes, member_name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tar:
        try:
            f = tar.extractfile(member_name)
        except KeyError as exc:
            raise KeyError(member_name) from exc
        if f is None:
            raise KeyError(member_name)
        return f.read()


def load_dossier_from_bundle(wire: bytes, key: bytes, agent_id: str) -> dict:
    archive = decrypt_bundle_archive(wire, key)
    raw = extract_member(archive, f'dossiers/{agent_id}.json')
    return json.loads(raw.decode('utf-8'))
