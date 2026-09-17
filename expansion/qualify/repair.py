"""Expansion repair — restore product integrity without erasing user state."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.canonical_dossiers import CANONICAL_AGENT_IDS, get_canonical_dossier
from expansion.migrations import apply_pending
from expansion.protected.keys import default_key_provider
from expansion.protected.loader import BUNDLE_KEY_NAME, ProtectedResourceLoader
from expansion.protected.verify import verify_protected_package
from expansion.rooms import RoomRegistry
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class RepairItem:
    check: str
    status: str  # ok | repaired | failed | skipped
    detail: str = ''


@dataclass
class RepairReport:
    ok: bool
    items: list = field(default_factory=list)
    preserve_user_data: bool = True

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'preserve_user_data': True,
            'items': [asdict(i) if hasattr(i, '__dataclass_fields__') else i for i in self.items],
        }


def repair_expansion(
    layout: Optional[StateLayout] = None,
    *,
    package_dir: Optional[Path] = None,
    public_key_pem: Optional[bytes] = None,
    channel: str = 'dev',
) -> RepairReport:
    """Validate and safely repair Expansion product/runtime state.

    Must NOT erase memories, relationships, journal, diary, living dossier,
    jobs, or owner preferences.
    """
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    items: list[RepairItem] = []

    # Snapshot counts to prove non-destruction
    before = _user_counts(layout)

    # Roster
    rt = ExpansionRuntime(layout)
    if rt.expansion_enabled() and len(rt.load_roster()) >= 5:
        items.append(RepairItem('agent_roster', 'ok', 'five agents present'))
    else:
        items.append(RepairItem('agent_roster', 'failed', 'roster incomplete — re-bootstrap required'))

    # Canonical data (dev channel plaintext SoT)
    try:
        for aid in CANONICAL_AGENT_IDS:
            get_canonical_dossier(aid, layout)
        items.append(RepairItem('canonical_data', 'ok', 'dossiers load'))
    except Exception as exc:  # noqa: BLE001
        items.append(RepairItem('canonical_data', 'failed', str(exc)))

    # Rooms registry
    try:
        rooms = RoomRegistry(layout).seed_defaults()
        items.append(RepairItem('room_registry', 'repaired' if rooms else 'ok', f'{len(rooms)} rooms'))
    except Exception as exc:  # noqa: BLE001
        items.append(RepairItem('room_registry', 'failed', str(exc)))

    # Migrations idempotent
    try:
        apply_pending(layout)
        items.append(RepairItem('migrations', 'ok', 'pending applied/idempotent'))
    except Exception as exc:  # noqa: BLE001
        items.append(RepairItem('migrations', 'failed', str(exc)))

    # Protected package if present
    pkg = package_dir
    if pkg is None:
        cur = layout.package_versions_root / 'current.json'
        if cur.is_file():
            meta = json.loads(cur.read_text(encoding='utf-8'))
            pkg = Path(meta.get('path') or '')
    if pkg and Path(pkg).is_dir() and (Path(pkg) / 'PACKAGE_MANIFEST.json').is_file():
        if public_key_pem and (Path(pkg) / 'signing-public.pem').is_file():
            public_key_pem = public_key_pem or (Path(pkg) / 'signing-public.pem').read_bytes()
        key_pem = public_key_pem
        if key_pem is None and (Path(pkg) / 'signing-public.pem').is_file():
            key_pem = (Path(pkg) / 'signing-public.pem').read_bytes()
        vr = verify_protected_package(Path(pkg), public_key_pem=key_pem)
        items.append(RepairItem(
            'protected_bundle',
            'ok' if vr.ok else 'failed',
            '; '.join(vr.errors) or 'verified',
        ))
        # Key access
        kp = default_key_provider(layout)
        if kp.exists(BUNDLE_KEY_NAME):
            items.append(RepairItem('local_key_access', 'ok', 'bundle key present'))
            if channel == 'protected' and vr.ok:
                try:
                    ProtectedResourceLoader(
                        layout=layout, key_provider=kp, channel='protected',
                        package_dir=Path(pkg),
                    ).load_canonical_dossier('aria')
                    items.append(RepairItem('bundle_decrypt', 'ok', 'aria loads'))
                except Exception as exc:  # noqa: BLE001
                    items.append(RepairItem('bundle_decrypt', 'failed', str(exc)))
        else:
            items.append(RepairItem(
                'local_key_access',
                'failed' if channel == 'protected' else 'skipped',
                'bundle key missing',
            ))
    else:
        items.append(RepairItem('protected_bundle', 'skipped', 'no staged protected package'))

    # Codec readiness
    try:
        if rt.expansion_enabled():
            ctx = rt.assemble_context('aria')
            items.append(RepairItem('codec_readiness', 'ok', f'context {len(ctx.system_prompt)} chars'))
        else:
            items.append(RepairItem('codec_readiness', 'skipped', 'expansion not enabled'))
    except Exception as exc:  # noqa: BLE001
        items.append(RepairItem('codec_readiness', 'failed', str(exc)))

    after = _user_counts(layout)
    if after != before:
        items.append(RepairItem('user_data_preserved', 'failed', f'counts changed {before} -> {after}'))
    else:
        items.append(RepairItem('user_data_preserved', 'ok', str(after)))

    ok = not any(i.status == 'failed' for i in items if i.check != 'protected_bundle')
    # Soft-fail protected when skipped
    hard_fail = [i for i in items if i.status == 'failed' and i.check in (
        'agent_roster', 'canonical_data', 'user_data_preserved', 'migrations', 'bundle_decrypt',
    )]
    return RepairReport(ok=not hard_fail, items=items)


def _user_counts(layout: StateLayout) -> dict:
    def _n(path: Path, glob: str) -> int:
        return len(list(path.glob(glob))) if path.exists() else 0
    return {
        'emotions': _n(layout.user_emotions, '*.json'),
        'relationships': _n(layout.user_relationships, '*.json'),
        'memory_files': _n(layout.user_memory, '*.jsonl'),
        'journals': _n(layout.user_journals, '*.jsonl'),
        'diaries': _n(layout.user_diaries, '*.jsonl'),
        'living': _n(layout.user_living_dossiers, '*.json'),
    }
