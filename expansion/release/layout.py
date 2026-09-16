"""Release package layout helpers (P3I).

Conceptual layout:

  product/
    PACKAGE_MANIFEST.json
    runtime/
    protected-bundle.enc
    signature metadata (in manifest)

  user/
    memory, journal, diary, relationships, jobs, living dossier, preferences

  secrets/
    platform-protected credentials/key blobs

No plaintext prompts/personas in protected release install directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReleaseLayout:
    root: Path
    manifest: Path
    runtime_dir: Path
    protected_bundle: Path
    public_key: Path

    @staticmethod
    def at(root: Path) -> 'ReleaseLayout':
        root = Path(root)
        return ReleaseLayout(
            root=root,
            manifest=root / 'PACKAGE_MANIFEST.json',
            runtime_dir=root / 'runtime',
            protected_bundle=root / 'protected-bundle.enc',
            public_key=root / 'signing-public.pem',
        )


def assert_no_plaintext_dossiers_in_release(root: Path) -> list:
    """Return errors if release tree exposes plaintext dossier JSON."""
    errors = []
    for path in Path(root).rglob('*.json'):
        if path.parent.name == 'dossiers' and 'staging_src' not in path.parts:
            errors.append(f'plaintext dossier in release tree: {path}')
    return errors
