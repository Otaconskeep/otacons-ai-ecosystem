"""Protected package verification — fail safe, preserve user data."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from expansion.manifest import load_manifest, verify_artifact_hashes
from expansion.protected.signing import verify_manifest_signature


@dataclass
class VerifyResult:
    ok: bool
    errors: list = field(default_factory=list)
    channel: str = ''
    action: str = ''  # continue | repair | reinstall
    preserve_user_data: bool = True

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'errors': list(self.errors),
            'channel': self.channel,
            'action': self.action,
            'preserve_user_data': True,
            'message': (
                'Verification failed — user data preserved. Repair or reinstall Expansion package.'
                if not self.ok else 'ok'
            ),
        }


def verify_protected_package(
    package_root: Path,
    *,
    manifest_path: Optional[Path] = None,
    public_key_pem: Optional[bytes] = None,
) -> VerifyResult:
    """Verify signed manifest + artifact hashes. Never deletes user state."""
    manifest_path = manifest_path or (package_root / 'PACKAGE_MANIFEST.json')
    if not manifest_path.is_file():
        return VerifyResult(
            ok=False, errors=['manifest missing'], action='reinstall', channel='unknown',
        )
    try:
        m = load_manifest(manifest_path)
    except Exception as exc:  # noqa: BLE001
        return VerifyResult(
            ok=False, errors=[f'manifest unreadable: {exc}'], action='reinstall',
        )
    errors = list(m.validate())
    if m.channel == 'protected':
        if not public_key_pem:
            errors.append('public signing key required for protected channel')
        else:
            errors.extend(verify_manifest_signature(m, public_key_pem))
        errors.extend(verify_artifact_hashes(m, package_root))
    elif m.channel == 'dev':
        if m.artifacts:
            errors.extend(verify_artifact_hashes(m, package_root))
    ok = not errors
    return VerifyResult(
        ok=ok,
        errors=errors,
        channel=m.channel,
        action='continue' if ok else 'repair',
        preserve_user_data=True,
    )


def reject_tampered(package_root: Path, public_key_pem: bytes) -> VerifyResult:
    result = verify_protected_package(package_root, public_key_pem=public_key_pem)
    if not result.ok:
        result.action = 'reinstall'
    return result
