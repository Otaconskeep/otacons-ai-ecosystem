"""Migration engine skeleton for Expansion persisted shapes.

Migrations are version-tagged, backed up before destructive changes, and
must never silently discard unknown data. Update flow snapshots user state,
stages the new package, runs migrations, health-checks, then commits —
failure rolls back to the previous known-good version.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import MIGRATION_ENGINE_VERSION, current_versions

MigrationFn = Callable[[StateLayout], None]


@dataclass
class Migration:
    migration_id: str
    description: str
    from_agent_schema: int
    to_agent_schema: int
    apply: Optional[MigrationFn] = None  # None = no-op placeholder registered for ordering


@dataclass
class MigrationRecord:
    migration_id: str
    applied_at: float
    from_agent_schema: int
    to_agent_schema: int
    success: bool
    notes: str = ''


@dataclass
class MigrationPlan:
    engine_version: int
    pending: list = field(default_factory=list)  # migration_ids
    applied: list = field(default_factory=list)  # MigrationRecord dicts


# Registry of known migrations. P0 ships the identity/no-op baseline only.
_REGISTRY: list[Migration] = [
    Migration(
        migration_id='m000_baseline',
        description='P0 baseline — no on-disk transform; establishes migration ledger',
        from_agent_schema=1,
        to_agent_schema=1,
        apply=None,
    ),
]


def registered_migrations() -> list[Migration]:
    return list(_REGISTRY)


def ledger_path(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    return layout.user_migrations / 'ledger.json'


def load_ledger(layout: Optional[StateLayout] = None) -> MigrationPlan:
    path = ledger_path(layout)
    if not path.exists():
        return MigrationPlan(engine_version=MIGRATION_ENGINE_VERSION)
    data = json.loads(path.read_text(encoding='utf-8'))
    return MigrationPlan(
        engine_version=int(data.get('engine_version', MIGRATION_ENGINE_VERSION)),
        pending=list(data.get('pending') or []),
        applied=list(data.get('applied') or []),
    )


def save_ledger(plan: MigrationPlan, layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.user_migrations.mkdir(parents=True, exist_ok=True)
    path = ledger_path(layout)
    path.write_text(json.dumps(asdict(plan), indent=2) + '\n', encoding='utf-8')
    return path


def snapshot_user_state(layout: Optional[StateLayout] = None, label: str = '') -> Path:
    """Copy user config+data trees into a timestamped snapshot for rollback."""
    layout = layout or resolve_layout()
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    label = label or 'pre-migrate'
    snap_root = layout.user_data_root / 'snapshots' / f'{stamp}_{label}'
    snap_root.mkdir(parents=True, exist_ok=True)
    for src, name in (
        (layout.user_config_root, 'config'),
        (layout.user_data_root, 'data'),
    ):
        if not src.exists():
            continue
        dest = snap_root / name
        if src.resolve() == layout.user_data_root.resolve() and name == 'data':
            # Avoid recursively copying snapshots into themselves
            dest.mkdir(parents=True, exist_ok=True)
            for child in src.iterdir():
                if child.name == 'snapshots':
                    continue
                target = dest / child.name
                if child.is_dir():
                    shutil.copytree(child, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, target)
        else:
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
    meta = {
        'created_at': time.time(),
        'label': label,
        'versions': current_versions().to_dict(),
    }
    (snap_root / 'SNAPSHOT.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return snap_root


def pending_migrations(layout: Optional[StateLayout] = None) -> list[Migration]:
    plan = load_ledger(layout)
    applied_ids = {r['migration_id'] if isinstance(r, dict) else r.migration_id for r in plan.applied}
    return [m for m in _REGISTRY if m.migration_id not in applied_ids]


def apply_pending(layout: Optional[StateLayout] = None, *, dry_run: bool = False) -> MigrationPlan:
    """Apply pending migrations in registry order. Snapshots first unless dry_run."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    plan = load_ledger(layout)
    pending = pending_migrations(layout)
    if not pending:
        save_ledger(plan, layout)
        return plan
    if not dry_run:
        snapshot_user_state(layout, label='pre-migrate')
    for m in pending:
        notes = 'dry_run' if dry_run else ''
        success = True
        if not dry_run and m.apply is not None:
            try:
                m.apply(layout)
            except Exception as exc:  # noqa: BLE001 — record and stop
                success = False
                notes = str(exc)
                plan.applied.append(asdict(MigrationRecord(
                    migration_id=m.migration_id,
                    applied_at=time.time(),
                    from_agent_schema=m.from_agent_schema,
                    to_agent_schema=m.to_agent_schema,
                    success=False,
                    notes=notes,
                )))
                save_ledger(plan, layout)
                raise
        if not dry_run:
            plan.applied.append(asdict(MigrationRecord(
                migration_id=m.migration_id,
                applied_at=time.time(),
                from_agent_schema=m.from_agent_schema,
                to_agent_schema=m.to_agent_schema,
                success=success,
                notes=notes or 'ok',
            )))
    plan.pending = [m.migration_id for m in pending_migrations(layout)]
    if not dry_run:
        save_ledger(plan, layout)
    return plan
