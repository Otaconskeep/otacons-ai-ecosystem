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
def _m001_p2_living(layout: StateLayout) -> None:
    """Ensure P2 directories + room registry exist without touching emotion/relationship files."""
    layout.ensure_user_dirs()
    (layout.user_journals).mkdir(parents=True, exist_ok=True)
    (layout.user_diaries).mkdir(parents=True, exist_ok=True)
    (layout.user_jobs).mkdir(parents=True, exist_ok=True)
    (layout.user_living_dossiers).mkdir(parents=True, exist_ok=True)
    (layout.user_pages).mkdir(parents=True, exist_ok=True)
    (layout.user_data_root / 'vulnerabilities').mkdir(parents=True, exist_ok=True)
    from expansion.rooms import RoomRegistry
    RoomRegistry(layout).seed_defaults()


_STOCK_PERSONA_MARKERS = (
    'command coordinator of this keep',
    'greetings… how may i assist',
    'soften only for the operator',
    'human court diction',
)


def _m002_behavior_spine_personas(layout: StateLayout) -> None:
    """Refresh stock Aria–Sentry personas to Keep-parity work-first voice.

    Only overwrites personas that still match the old robotic stock text.
    Owner-customized personas (no stock markers) are left alone. Learning,
    emotion, and relationship stores are never touched.
    """
    from expansion.seed_defaults import build_default_roster
    from expansion.schema import to_dict

    layout.ensure_user_dirs()
    agents_dir = layout.user_agents
    agents_dir.mkdir(parents=True, exist_ok=True)
    fresh = {a.agent_id: a for a in build_default_roster()}
    for agent_id, agent in fresh.items():
        path = agents_dir / f'default-{agent_id}.json'
        if not path.exists():
            path.write_text(json.dumps(to_dict(agent), indent=2) + '\n', encoding='utf-8')
            continue
        try:
            existing = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        persona = str(existing.get('persona') or '')
        low = persona.lower()
        if not any(m in low for m in _STOCK_PERSONA_MARKERS):
            # Not old stock — treat as owner customization
            continue
        existing['persona'] = agent.persona
        existing['updated_at'] = time.time()
        path.write_text(json.dumps(existing, indent=2) + '\n', encoding='utf-8')


_REGISTRY: list[Migration] = [
    Migration(
        migration_id='m000_baseline',
        description='P0 baseline — no on-disk transform; establishes migration ledger',
        from_agent_schema=1,
        to_agent_schema=1,
        apply=None,
    ),
    Migration(
        migration_id='m001_p2_living_layer',
        description='P2 living layer dirs + room registry; preserves emotion/relationships/memories',
        from_agent_schema=1,
        to_agent_schema=1,
        apply=_m001_p2_living,
    ),
    Migration(
        migration_id='m002_behavior_spine_personas',
        description='Refresh stock personas to work-first Keep-parity voice; preserve custom personas + memory',
        from_agent_schema=1,
        to_agent_schema=1,
        apply=_m002_behavior_spine_personas,
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
    """Migrations not yet successfully applied.

    Failed attempts stay in the ledger for history but do NOT count as applied,
    so they remain pending and can be retried.
    """
    plan = load_ledger(layout)
    applied_ids = set()
    for r in plan.applied:
        if isinstance(r, dict):
            if r.get('success', True):
                applied_ids.add(r.get('migration_id'))
        else:
            if getattr(r, 'success', True):
                applied_ids.add(r.migration_id)
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
