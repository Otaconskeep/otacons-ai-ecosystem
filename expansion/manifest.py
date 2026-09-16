"""Signed package manifest contract for Keep Expansion releases.

Dev/foundation builds may omit signatures and encryption. Production
protected releases must populate signature, hashes, and encrypted bundle
descriptors. Startup/update verifies integrity against this contract.

Tamper response: fail safely and offer repair/reinstall.
Never delete user data or damage the machine.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.versions import EXPANSION_VERSION, MANIFEST_SCHEMA_VERSION, current_versions

# Authenticated encryption algorithms allowed in production packages.
ALLOWED_AEAD = ('AES-256-GCM', 'XChaCha20-Poly1305')


@dataclass
class ArtifactRef:
    path: str
    sha256: str
    role: str  # runtime | protected_module | encrypted_bundle | asset | schema
    encrypted: bool = False
    aead: str = ''  # required when encrypted=True


@dataclass
class PackageManifest:
    manifest_schema_version: int
    product: str
    expansion_version: str
    core_version_min: str
    agent_schema_version: int
    created_at: float
    channel: str  # public | protected | dev
    artifacts: list = field(default_factory=list)  # list[ArtifactRef] or dicts
    signature: str = ''           # detached signature over canonical bytes (prod)
    signing_key_id: str = ''
    encryption: dict = field(default_factory=dict)  # {aead, kdf, notes} — no raw keys
    previous_version: str = ''
    notes: str = ''
    package_id: str = 'otacon-expansion'
    build_id: str = ''
    release_channel: str = ''  # mirrors channel; explicit for release docs
    component_hashes: dict = field(default_factory=dict)  # logical component -> sha256

    def validate(self) -> list:
        errors = []
        if self.manifest_schema_version != MANIFEST_SCHEMA_VERSION:
            errors.append(
                f'unsupported manifest_schema_version {self.manifest_schema_version}'
            )
        if self.product != 'otacon-expansion':
            errors.append(f'unexpected product {self.product!r}')
        if not self.expansion_version:
            errors.append('expansion_version required')
        if self.channel not in ('public', 'protected', 'dev'):
            errors.append(f'invalid channel {self.channel!r}')
        if self.package_id and self.package_id != 'otacon-expansion':
            errors.append(f'unexpected package_id {self.package_id!r}')
        for i, art in enumerate(self.artifacts):
            a = art if isinstance(art, ArtifactRef) else ArtifactRef(**art)
            if not a.path or not a.sha256:
                errors.append(f'artifact[{i}] missing path or sha256')
            if len(a.sha256) != 64:
                errors.append(f'artifact[{i}] sha256 must be 64 hex chars')
            if a.encrypted:
                if a.aead not in ALLOWED_AEAD:
                    errors.append(
                        f'artifact[{i}] encrypted but aead {a.aead!r} not in {ALLOWED_AEAD}'
                    )
        if self.channel == 'protected':
            if not self.signature or not self.signing_key_id:
                errors.append('protected channel requires signature and signing_key_id')
            if not self.artifacts:
                errors.append('protected channel requires at least one artifact')
            if not self.build_id:
                errors.append('protected channel requires build_id')
        enc = self.encryption or {}
        if enc.get('aead') and enc['aead'] not in ALLOWED_AEAD:
            errors.append(f"encryption.aead must be one of {ALLOWED_AEAD}")
        # Never allow plaintext key material in the manifest
        for forbidden in ('key', 'password', 'secret', 'private_key'):
            if forbidden in enc:
                errors.append(f'encryption must not contain {forbidden!r}')
        return errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def build_dev_manifest(
    *,
    expansion_version: str = EXPANSION_VERSION,
    core_version_min: str = '0.1.0',
    artifacts: Optional[list] = None,
    notes: str = 'foundation / developer build — not a protected release',
) -> PackageManifest:
    versions = current_versions()
    return PackageManifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        product='otacon-expansion',
        expansion_version=expansion_version,
        core_version_min=core_version_min,
        agent_schema_version=versions.agent_schema,
        created_at=time.time(),
        channel='dev',
        artifacts=artifacts or [],
        notes=notes,
    )


def to_dict(m: PackageManifest) -> dict:
    d = asdict(m)
    # Normalize ArtifactRef dataclasses if present
    arts = []
    for a in m.artifacts:
        arts.append(asdict(a) if isinstance(a, ArtifactRef) else dict(a))
    d['artifacts'] = arts
    return d


def from_dict(d: dict) -> PackageManifest:
    d = dict(d)
    arts = []
    for a in d.get('artifacts') or []:
        arts.append(ArtifactRef(**a) if isinstance(a, dict) else a)
    d['artifacts'] = arts
    fields = PackageManifest.__dataclass_fields__
    return PackageManifest(**{k: v for k, v in d.items() if k in fields})


def save_manifest(m: PackageManifest, path: Path) -> Path:
    errors = m.validate()
    if errors:
        raise ValueError('; '.join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(m), indent=2) + '\n', encoding='utf-8')
    return path


def load_manifest(path: Path) -> PackageManifest:
    return from_dict(json.loads(path.read_text(encoding='utf-8')))


def verify_artifact_hashes(m: PackageManifest, root: Path) -> list:
    """Return list of error strings; empty means all present artifacts match."""
    errors = []
    for a in m.artifacts:
        art = a if isinstance(a, ArtifactRef) else ArtifactRef(**a)
        p = root / art.path
        if not p.is_file():
            errors.append(f'missing artifact: {art.path}')
            continue
        digest = sha256_file(p)
        if digest != art.sha256:
            errors.append(f'hash mismatch: {art.path}')
    return errors
