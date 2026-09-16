"""Expansion release build pipeline (dev vs protected).

Development:
  source → tests → normal runnable tree (plaintext product/dossiers SoT)

Release:
  private source → tests → (optional compile) → minify frontend →
  strip maps → package protected resources → compress → encrypt →
  sign → smoke-test protected artifact

Build must be reproducible from clean checkout + CI secrets.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.manifest import (
    ArtifactRef,
    PackageManifest,
    save_manifest,
    sha256_file,
)
from expansion.protected.bundle import write_protected_bundle
from expansion.protected.keys import KeyProvider, default_key_provider
from expansion.protected.loader import BUNDLE_KEY_NAME
from expansion.protected.signing import generate_signing_keypair, sign_manifest
from expansion.release.frontend import harden_frontend_tree
from expansion.release.layout import ReleaseLayout, assert_no_plaintext_dossiers_in_release
from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import EXPANSION_VERSION, MANIFEST_SCHEMA_VERSION, current_versions


@dataclass
class BuildResult:
    channel: str
    out_dir: Path
    manifest_path: Path
    build_id: str
    smoke_ok: bool
    notes: list = field(default_factory=list)
    public_key_pem: bytes = b''

    def to_dict(self) -> dict:
        d = asdict(self)
        d['public_key_pem'] = ''  # never serialize key material in reports by default
        d['has_public_key'] = bool(self.public_key_pem)
        return d


def build_dev_tree(out_dir: Path, layout: Optional[StateLayout] = None) -> BuildResult:
    """Copy runnable Expansion product tree for development (plaintext dossiers OK)."""
    layout = layout or resolve_layout()
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    src_product = layout.product_root / 'product'
    dst_product = out_dir / 'product'
    if src_product.is_dir():
        shutil.copytree(src_product, dst_product)
    build_id = f'dev-{uuid.uuid4().hex[:10]}'
    versions = current_versions()
    m = PackageManifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        product='otacon-expansion',
        expansion_version=EXPANSION_VERSION,
        core_version_min='0.1.0',
        agent_schema_version=versions.agent_schema,
        created_at=time.time(),
        channel='dev',
        build_id=build_id,
        release_channel='dev',
        notes='development build — plaintext product dossiers are SoT',
    )
    # Hash dossiers if present
    dossiers = dst_product / 'dossiers'
    arts = []
    component_hashes = {}
    if dossiers.is_dir():
        for path in sorted(dossiers.glob('*.json')):
            digest = sha256_file(path)
            rel = f'product/dossiers/{path.name}'
            arts.append(ArtifactRef(path=rel, sha256=digest, role='schema'))
            component_hashes[path.stem] = digest
    m.artifacts = arts
    m.component_hashes = component_hashes
    manifest_path = save_manifest(m, out_dir / 'PACKAGE_MANIFEST.json')
    return BuildResult(
        channel='dev', out_dir=out_dir, manifest_path=manifest_path,
        build_id=build_id, smoke_ok=True, notes=['dev tree built'],
    )


def build_protected_release(
    out_dir: Path,
    layout: Optional[StateLayout] = None,
    *,
    key_provider: Optional[KeyProvider] = None,
    signing_private_pem: Optional[bytes] = None,
    signing_public_pem: Optional[bytes] = None,
    key_id: str = 'release-1',
    minify_frontend_from: Optional[Path] = None,
) -> BuildResult:
    """Produce a signed, encrypted Expansion package under out_dir."""
    layout = layout or resolve_layout()
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rl = ReleaseLayout.at(out_dir)
    rl.runtime_dir.mkdir(parents=True)
    notes = []

    # Frontend hardening (optional source UI tree)
    if minify_frontend_from and Path(minify_frontend_from).is_dir():
        dest_ui = rl.runtime_dir / 'ui'
        harden_frontend_tree(Path(minify_frontend_from), dest_ui)
        notes.append('frontend hardened into runtime/ui')

    # Encrypt product resources (dossiers etc.) — no plaintext dossiers in release root
    bundle = write_protected_bundle(out_dir, layout=layout)
    notes.append(f'encrypted {len(bundle.member_names)} members')

    # Store bundle key via key provider (not in package tree / logs)
    kp = key_provider or default_key_provider(layout)
    kp.store(BUNDLE_KEY_NAME, bundle.key)

    # Signing keys
    if signing_private_pem is None or signing_public_pem is None:
        pair = generate_signing_keypair(key_id=key_id)
        signing_private_pem = pair.private_key_pem
        signing_public_pem = pair.public_key_pem
        notes.append('generated ephemeral signing keypair for this build')
    rl.public_key.write_bytes(signing_public_pem)

    build_id = f'prot-{uuid.uuid4().hex[:12]}'
    versions = current_versions()
    arts = [
        ArtifactRef(
            path=bundle.bundle_path.name,
            sha256=bundle.sha256,
            role='encrypted_bundle',
            encrypted=True,
            aead=bundle.aead,
        )
    ]
    if (rl.runtime_dir / 'ui').is_dir():
        # Fingerprint hardened UI tree into a single hash file artifact
        h = hashlib.sha256()
        for path in sorted((rl.runtime_dir / 'ui').rglob('*')):
            if path.is_file():
                h.update(path.as_posix().encode())
                h.update(path.read_bytes())
        digest = h.hexdigest()
        stamp = rl.runtime_dir / 'ui.sha256'
        stamp.write_text(digest + '\n', encoding='utf-8')
        arts.append(ArtifactRef(
            path='runtime/ui.sha256',
            sha256=sha256_file(stamp),
            role='runtime',
        ))

    m = PackageManifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        product='otacon-expansion',
        package_id='otacon-expansion',
        expansion_version=EXPANSION_VERSION,
        core_version_min='0.1.0',
        agent_schema_version=versions.agent_schema,
        created_at=time.time(),
        channel='protected',
        release_channel='protected',
        build_id=build_id,
        artifacts=arts,
        encryption={
            'aead': bundle.aead,
            'kdf': 'none-for-bundle-key',
            'notes': 'Bundle key is random high-entropy; stored via KeyProvider, not in package.',
        },
        component_hashes={name: hashlib.sha256(name.encode()).hexdigest() for name in bundle.member_names[:20]},
        notes='protected release — dossiers only inside encrypted bundle',
    )
    sign_manifest(m, signing_private_pem, key_id=key_id)
    manifest_path = save_manifest(m, rl.manifest)

    # Ensure no plaintext dossiers leaked
    leak = assert_no_plaintext_dossiers_in_release(out_dir)
    smoke_ok = not leak
    if leak:
        notes.extend(leak)

    # Smoke: decrypt one dossier
    try:
        from expansion.protected.loader import ProtectedResourceLoader
        loader = ProtectedResourceLoader(
            layout=layout, key_provider=kp, channel='protected', package_dir=out_dir,
        )
        d = loader.load_canonical_dossier('aria')
        assert d.agent_id == 'aria'
        notes.append('smoke: aria dossier decrypt/load ok')
        smoke_ok = smoke_ok and True
    except Exception as exc:  # noqa: BLE001
        notes.append(f'smoke failed: {exc}')
        smoke_ok = False

    return BuildResult(
        channel='protected',
        out_dir=out_dir,
        manifest_path=manifest_path,
        build_id=build_id,
        smoke_ok=smoke_ok,
        notes=notes,
        public_key_pem=signing_public_pem,
    )
