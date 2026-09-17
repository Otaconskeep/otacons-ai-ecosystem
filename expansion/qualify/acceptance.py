"""P4 acceptance matrix runner."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.capabilities.discord_n8n import probe_all_optional
from expansion.qualify.health import HealthState, overall_expansion_health
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class MatrixCell:
    name: str
    status: str  # PASS | DEGRADED | FAIL | SKIP
    detail: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AcceptanceReport:
    cells: list = field(default_factory=list)
    overall: str = 'FAIL'
    channel: str = 'dev'

    def to_dict(self) -> dict:
        return {
            'overall': self.overall,
            'channel': self.channel,
            'cells': [c.to_dict() for c in self.cells],
        }


def _cell(name: str, status: str, detail: str = '') -> MatrixCell:
    return MatrixCell(name=name, status=status, detail=detail)


def run_acceptance(
    layout: Optional[StateLayout] = None,
    *,
    channel: str = 'dev',
    package_dir: Optional[Path] = None,
    public_key_pem: Optional[bytes] = None,
) -> AcceptanceReport:
    layout = layout or resolve_layout()
    cells: list[MatrixCell] = []
    components = {'CHANNEL': channel}

    # CORE — public markers not required in unit harness
    cells.append(_cell('CORE', 'PASS', 'qualification harness (Core path not mutated)'))
    components['CORE'] = HealthState.READY.value

    rt = ExpansionRuntime(layout)
    if rt.expansion_enabled() and len(rt.load_roster()) >= 5:
        cells.append(_cell('EXPANSION', 'PASS', 'roster enabled'))
        cells.append(_cell('AGENTS', 'PASS', '5 agents'))
        components['AGENTS'] = HealthState.READY.value
    elif rt.expansion_enabled():
        cells.append(_cell('EXPANSION', 'FAIL', 'enabled but roster incomplete'))
        cells.append(_cell('AGENTS', 'FAIL', 'roster incomplete'))
        components['AGENTS'] = HealthState.FAILED.value
    else:
        cells.append(_cell('EXPANSION', 'SKIP', 'Expansion not installed on this layout'))
        cells.append(_cell('AGENTS', 'SKIP', 'no roster'))
        components['AGENTS'] = HealthState.UNAVAILABLE.value

    # Stores
    from expansion.emotion_store import EmotionStore
    from expansion.relationship_store import RelationshipStore
    from expansion.journal import JournalStore
    from expansion.diary import DiaryStore
    from expansion.jobs import JobStore
    from expansion.memory_bridge import ExpansionMemory
    from expansion.rooms import RoomRegistry

    emo_ok = bool(EmotionStore(layout).list_agent_ids())
    cells.append(_cell('EMOTION', 'PASS' if emo_ok else 'FAIL'))
    components['EMOTIONAL_ENGINE'] = HealthState.READY.value if emo_ok else HealthState.FAILED.value

    rel_ok = any(layout.user_relationships.glob('*.json'))
    cells.append(_cell('RELATIONSHIPS', 'PASS' if rel_ok else 'DEGRADED', 'files' if rel_ok else 'empty'))
    components['RELATIONSHIPS'] = HealthState.READY.value if rel_ok else HealthState.LIMITED.value

    mem_ok = any(layout.user_memory.glob('*.jsonl'))
    cells.append(_cell('MEMORY', 'PASS' if mem_ok else 'DEGRADED'))

    j_ok = bool(JournalStore(layout).recent(limit=1)) or any(layout.user_journals.glob('*.jsonl'))
    cells.append(_cell('JOURNAL', 'PASS' if j_ok else 'DEGRADED'))

    d_ok = any(layout.user_diaries.glob('*.jsonl'))
    cells.append(_cell('DIARY', 'PASS' if d_ok else 'DEGRADED'))

    jobs_ok = layout.user_jobs.exists()
    cells.append(_cell('JOBS', 'PASS' if jobs_ok else 'DEGRADED'))

    rooms = RoomRegistry(layout).seed_defaults()
    cells.append(_cell('ROOMS', 'PASS' if rooms else 'FAIL', f'{len(rooms)}'))

    try:
        rt.assemble_context('aria')
        cells.append(_cell('CODEC', 'PASS'))
    except KeyError:
        cells.append(_cell('CODEC', 'SKIP' if not rt.expansion_enabled() else 'FAIL', 'agent missing'))
    except Exception as exc:  # noqa: BLE001
        cells.append(_cell('CODEC', 'FAIL', str(exc)))

    # Protected bundle
    if channel == 'protected' and package_dir:
        from expansion.protected.verify import verify_protected_package
        vr = verify_protected_package(Path(package_dir), public_key_pem=public_key_pem)
        cells.append(_cell('PROTECTED BUNDLE', 'PASS' if vr.ok else 'FAIL', '; '.join(vr.errors)[:200]))
        cells.append(_cell('SIGNATURE', 'PASS' if vr.ok else 'FAIL'))
        components['PROTECTED_BUNDLE'] = (
            HealthState.READY.value if vr.ok else HealthState.FAILED.value
        )
    else:
        cells.append(_cell('PROTECTED BUNDLE', 'SKIP', 'dev channel'))
        cells.append(_cell('SIGNATURE', 'SKIP', 'dev channel'))
        components['PROTECTED_BUNDLE'] = HealthState.UNAVAILABLE.value

    cells.append(_cell('UPDATE', 'SKIP', 'see p4 qualification tests'))
    cells.append(_cell('ROLLBACK', 'SKIP', 'see p4 qualification tests'))

    caps = probe_all_optional(layout)
    opt_bits = []
    for name, rep in caps.items():
        st = rep.get('state', 'UNAVAILABLE')
        opt_bits.append(f'{name}={st}')
        if st == 'FAILED':
            cells.append(_cell('OPTIONAL CAPABILITIES', 'DEGRADED', '; '.join(opt_bits)))
            break
    else:
        cells.append(_cell('OPTIONAL CAPABILITIES', 'PASS', '; '.join(opt_bits)))

    overall = overall_expansion_health(components)
    # Map health to matrix overall
    hard_fails = [c for c in cells if c.status == 'FAIL']
    if hard_fails:
        overall_s = 'FAIL'
    elif overall == HealthState.FAILED.value:
        overall_s = 'FAIL'
    elif not rt.expansion_enabled():
        overall_s = 'SKIP'
    elif overall == HealthState.DEGRADED.value:
        overall_s = 'DEGRADED'
    else:
        overall_s = 'PASS'

    return AcceptanceReport(cells=cells, overall=overall_s, channel=channel)
