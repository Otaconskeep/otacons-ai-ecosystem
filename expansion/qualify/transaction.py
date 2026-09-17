"""Install/update transaction phases with explicit resume or rollback.

Phases (in order):
  precheck → download → signature_verification → package_decryption →
  staging → migration → service_startup → semantic_health →
  restart_health → commit

On interruption: detect persisted transaction and RESUME or ROLL BACK —
never guess.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

INSTALL_PHASES = (
    'precheck',
    'download',
    'signature_verification',
    'package_decryption',
    'staging',
    'migration',
    'service_startup',
    'semantic_health',
    'restart_health',
    'commit',
)


class TxStatus(str, Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    ROLLED_BACK = 'rolled_back'
    RESUMABLE = 'resumable'


@dataclass
class PhaseRecord:
    phase: str
    status: str  # pending|ok|failed|skipped
    detail: str = ''
    at: float = 0.0


@dataclass
class InstallTransaction:
    tx_id: str
    kind: str  # install | update | repair
    status: str
    created_at: float
    updated_at: float
    package_version: str = ''
    phases: list = field(default_factory=list)
    current_phase: str = ''
    error: str = ''
    snapshot_path: str = ''
    staged_path: str = ''
    previous_version: str = ''
    inject_fail_at: str = ''  # test hook: fail when entering this phase

    def phase_map(self) -> dict:
        out = {}
        for p in self.phases:
            d = p if isinstance(p, dict) else asdict(p)
            out[d['phase']] = d
        return out


def _tx_path(layout: StateLayout, tx_id: str) -> Path:
    return layout.user_migrations / 'transactions' / f'{tx_id}.json'


def _active_marker(layout: StateLayout) -> Path:
    return layout.user_migrations / 'transactions' / 'ACTIVE.json'


def new_transaction(
    kind: str = 'update',
    *,
    package_version: str = '',
    layout: Optional[StateLayout] = None,
    inject_fail_at: str = '',
) -> InstallTransaction:
    layout = layout or resolve_layout()
    now = time.time()
    tx = InstallTransaction(
        tx_id=f'tx_{uuid.uuid4().hex[:12]}',
        kind=kind,
        status=TxStatus.PENDING.value,
        created_at=now,
        updated_at=now,
        package_version=package_version,
        phases=[PhaseRecord(phase=p, status='pending') for p in INSTALL_PHASES],
        inject_fail_at=inject_fail_at,
    )
    save_transaction(tx, layout)
    return tx


def save_transaction(tx: InstallTransaction, layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    path = _tx_path(layout, tx.tx_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tx.updated_at = time.time()
    payload = asdict(tx)
    # normalize PhaseRecord
    payload['phases'] = [
        p if isinstance(p, dict) else asdict(p) for p in tx.phases
    ]
    atomic_write_json(path, payload)
    atomic_write_json(_active_marker(layout), {
        'tx_id': tx.tx_id,
        'status': tx.status,
        'kind': tx.kind,
        'updated_at': tx.updated_at,
    })
    return path


def load_transaction(tx_id: str, layout: Optional[StateLayout] = None) -> InstallTransaction:
    layout = layout or resolve_layout()
    raw = read_json(_tx_path(layout, tx_id), default=None)
    if not raw:
        raise KeyError(tx_id)
    return InstallTransaction(**{k: raw[k] for k in InstallTransaction.__dataclass_fields__ if k in raw})


def load_active_transaction(layout: Optional[StateLayout] = None) -> Optional[InstallTransaction]:
    layout = layout or resolve_layout()
    marker = read_json(_active_marker(layout), default=None)
    if not marker or not marker.get('tx_id'):
        return None
    try:
        return load_transaction(marker['tx_id'], layout)
    except KeyError:
        return None


def clear_active_marker(layout: Optional[StateLayout] = None) -> None:
    layout = layout or resolve_layout()
    path = _active_marker(layout)
    if path.is_file():
        path.unlink()


def _set_phase(tx: InstallTransaction, phase: str, status: str, detail: str = '') -> None:
    phases = []
    for p in tx.phases:
        d = dict(p) if isinstance(p, dict) else asdict(p)
        if d['phase'] == phase:
            d['status'] = status
            d['detail'] = detail
            d['at'] = time.time()
        phases.append(d)
    tx.phases = phases
    tx.current_phase = phase


PhaseHandler = Callable[[InstallTransaction, StateLayout], str]


def run_phases(
    tx: InstallTransaction,
    handlers: dict,
    layout: Optional[StateLayout] = None,
    *,
    stop_before_commit: bool = False,
) -> InstallTransaction:
    """Execute remaining pending phases. handlers[phase] -> detail string."""
    layout = layout or resolve_layout()
    tx.status = TxStatus.IN_PROGRESS.value
    save_transaction(tx, layout)
    try:
        for phase in INSTALL_PHASES:
            rec = tx.phase_map().get(phase) or {}
            if rec.get('status') == 'ok':
                continue
            if tx.inject_fail_at and tx.inject_fail_at == phase:
                _set_phase(tx, phase, 'failed', f'injected failure at {phase}')
                tx.status = TxStatus.FAILED.value
                tx.error = f'injected failure at {phase}'
                save_transaction(tx, layout)
                raise RuntimeError(tx.error)
            if stop_before_commit and phase == 'commit':
                tx.status = TxStatus.RESUMABLE.value
                save_transaction(tx, layout)
                return tx
            handler = handlers.get(phase)
            if handler is None:
                _set_phase(tx, phase, 'skipped', 'no handler')
            else:
                detail = handler(tx, layout) or 'ok'
                _set_phase(tx, phase, 'ok', detail)
            save_transaction(tx, layout)
        tx.status = TxStatus.COMPLETED.value
        save_transaction(tx, layout)
        clear_active_marker(layout)
        return tx
    except Exception as exc:
        if tx.status != TxStatus.FAILED.value:
            tx.status = TxStatus.FAILED.value
            tx.error = str(exc)
            if tx.current_phase:
                _set_phase(tx, tx.current_phase, 'failed', str(exc))
            save_transaction(tx, layout)
        raise


def decide_resume_or_rollback(tx: InstallTransaction) -> str:
    """Return 'resume' or 'rollback' — never guess."""
    if tx.status == TxStatus.COMPLETED.value:
        return 'noop'
    if tx.status in (TxStatus.PENDING.value, TxStatus.RESUMABLE.value):
        # Safe to resume if we have not committed and staging/migration may continue
        pm = tx.phase_map()
        if pm.get('commit', {}).get('status') == 'ok':
            return 'noop'
        if pm.get('staging', {}).get('status') == 'ok' and pm.get('migration', {}).get('status') != 'ok':
            return 'resume'
        if pm.get('migration', {}).get('status') == 'ok' and pm.get('commit', {}).get('status') != 'ok':
            # Migrated but not committed — resume health/commit if product staged,
            # else rollback to avoid half-live state
            if tx.staged_path and Path(tx.staged_path).is_dir():
                return 'resume'
            return 'rollback'
        if pm.get('staging', {}).get('status') != 'ok':
            return 'rollback'
        return 'resume'
    if tx.status == TxStatus.FAILED.value:
        pm = tx.phase_map()
        # Failure before staging mutation → rollback (clean)
        if pm.get('staging', {}).get('status') != 'ok':
            return 'rollback'
        # Failure after migration → rollback product pointer
        return 'rollback'
    if tx.status == TxStatus.IN_PROGRESS.value:
        # Unclean kill mid-phase — treat as resumable only if staging succeeded
        pm = tx.phase_map()
        if pm.get('staging', {}).get('status') == 'ok' and pm.get('commit', {}).get('status') != 'ok':
            return 'resume'
        return 'rollback'
    return 'rollback'


def mark_rolled_back(tx: InstallTransaction, layout: Optional[StateLayout] = None, detail: str = '') -> None:
    layout = layout or resolve_layout()
    tx.status = TxStatus.ROLLED_BACK.value
    tx.error = detail or tx.error
    save_transaction(tx, layout)
    clear_active_marker(layout)
