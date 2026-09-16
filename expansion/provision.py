"""Agent provisioning transaction skeleton (15 steps).

Creating an agent is one logical transaction. If a mid-step fails, the agent
is either rolled back or marked safely resumable — never left where the
Dashboard lists an agent Codec cannot use.

P0: skeleton with step registry, state machine, event emission, and
roll-forward markers. Heavy side effects (voice onnx verify, motion assets,
Discord) remain deferred stubs that record NOT_CONFIGURED / pending.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from expansion.events import EventBus, new_event
from expansion.schema import Agent, to_dict as agent_to_dict, validate_agent
from expansion.state_layout import StateLayout, resolve_layout

PROVISION_STEPS = (
    'roster_registration',
    'stable_agent_id',
    'persona_storage',
    'role_domain_assignment',
    'hierarchy_placement',
    'greeting_fast_path',
    'voice_binding',
    'motion_manifest',
    'emotional_state_init',
    'relationship_graph_init',
    'dossier_init',
    'journal_init',
    'room_ownership',
    'discord_routing',
    'decision_domain_registration',
)


class ProvisionStatus(str, Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    ROLLED_BACK = 'rolled_back'
    RESUMABLE = 'resumable'


@dataclass
class StepResult:
    step: str
    status: str
    detail: str = ''
    deferred: bool = False  # True = skeleton acknowledged; real work in later phase


@dataclass
class ProvisionTransaction:
    tx_id: str
    agent_id: str
    status: str
    created_at: float
    updated_at: float
    steps: list = field(default_factory=list)  # StepResult dicts
    error: str = ''
    agent_snapshot: dict = field(default_factory=dict)

    def step_map(self) -> dict:
        return {s['step'] if isinstance(s, dict) else s.step: s for s in self.steps}


StepHandler = Callable[['ProvisionContext'], StepResult]


@dataclass
class ProvisionContext:
    layout: StateLayout
    agent: Agent
    tx: ProvisionTransaction
    bus: EventBus


def _ok(step: str, detail: str = '', deferred: bool = False) -> StepResult:
    return StepResult(step=step, status='completed', detail=detail, deferred=deferred)


def _step_roster(ctx: ProvisionContext) -> StepResult:
    return _ok('roster_registration', 'agent accepted into transaction')


def _step_id(ctx: ProvisionContext) -> StepResult:
    if not ctx.agent.agent_id:
        return StepResult('stable_agent_id', 'failed', 'missing agent_id')
    return _ok('stable_agent_id', ctx.agent.agent_id)


def _step_persona(ctx: ProvisionContext) -> StepResult:
    errs = validate_agent(ctx.agent)
    if any('persona' in e for e in errs):
        return StepResult('persona_storage', 'failed', '; '.join(errs))
    return _ok('persona_storage', 'persona validated for storage')


def _step_role(ctx: ProvisionContext) -> StepResult:
    if not ctx.agent.role or not ctx.agent.domain:
        return StepResult('role_domain_assignment', 'failed', 'role/domain required')
    return _ok('role_domain_assignment', f'{ctx.agent.role}/{ctx.agent.domain}')


def _step_hierarchy(ctx: ProvisionContext) -> StepResult:
    if ctx.agent.reporting_to == ctx.agent.agent_id:
        return StepResult('hierarchy_placement', 'failed', 'self-report')
    return _ok('hierarchy_placement', f'reports_to={ctx.agent.reporting_to}')


def _step_emotion(ctx: ProvisionContext) -> StepResult:
    from expansion.canonical_dossiers import get_canonical_dossier
    from expansion.emotion_store import EmotionStore
    dossier = get_canonical_dossier(ctx.agent.agent_id)
    store = EmotionStore(ctx.layout)
    store.get_or_create(
        ctx.agent.agent_id,
        baseline=dossier.stress.emotional_baseline,
    )
    return _ok('emotional_state_init', 'emotional state persisted')


def _step_relationships(ctx: ProvisionContext) -> StepResult:
    from expansion.relationship_store import RelationshipStore
    store = RelationshipStore(ctx.layout)
    # Ensure edges to/from this agent against known defaults + user
    defaults = ['aria', 'vector', 'ledger', 'muse', 'sentry']
    for other in defaults:
        if other == ctx.agent.agent_id:
            continue
        store.get_or_create(ctx.agent.agent_id, other)
        store.get_or_create(other, ctx.agent.agent_id)
    store.get_or_create(ctx.agent.agent_id, 'user_primary', use_triangle_presets=False)
    store.get_or_create('user_primary', ctx.agent.agent_id, use_triangle_presets=False)
    return _ok('relationship_graph_init', 'directional edges initialized')


def _step_dossier(ctx: ProvisionContext) -> StepResult:
    from expansion.bootstrap import write_canonical_dossiers
    from expansion.living_dossier_init import init_empty_living_dossier
    write_canonical_dossiers(ctx.layout)
    init_empty_living_dossier(ctx.layout, ctx.agent.agent_id)
    return _ok('dossier_init', 'canonical + empty living dossier')


def _step_journal(ctx: ProvisionContext) -> StepResult:
    jpath = ctx.layout.user_journals / f'{ctx.agent.agent_id}.jsonl'
    dpath = ctx.layout.user_diaries / f'{ctx.agent.agent_id}.jsonl'
    jpath.parent.mkdir(parents=True, exist_ok=True)
    dpath.parent.mkdir(parents=True, exist_ok=True)
    if not jpath.exists():
        jpath.write_text('', encoding='utf-8')
    if not dpath.exists():
        dpath.write_text('', encoding='utf-8')
    return _ok('journal_init', 'journal/diary stores ready')


def _step_motion(ctx: ProvisionContext) -> StepResult:
    from expansion.motion_defaults import DEFAULT_MOTION, build_manifest
    from expansion.motion_manifest import validate_manifest
    from expansion.schema import MotionManifestRef
    ref = DEFAULT_MOTION.get(ctx.agent.agent_id)
    if ref:
        ctx.agent.motion_manifest = MotionManifestRef(
            manifest_id=ref.manifest_id,
            capability_level=ref.capability_level,
        )
        errors = validate_manifest(build_manifest(ctx.agent.agent_id))
        if errors:
            return StepResult('motion_manifest', 'failed', '; '.join(errors))
        return _ok('motion_manifest', ref.manifest_id)
    return _ok('motion_manifest', 'no default motion', deferred=True)


def _step_greeting(ctx: ProvisionContext) -> StepResult:
    # Fast-path registration recorded as a semantic memory cue
    from expansion.memory_bridge import ExpansionMemory, new_memory
    mem = ExpansionMemory(ctx.layout)
    mem.add(new_memory(
        ctx.agent.agent_id,
        f'greeting fast-path registered for {ctx.agent.display_name}',
        kind='working',
        source='provision',
        importance=0.4,
    ))
    return _ok('greeting_fast_path', 'registered')


def _step_voice(ctx: ProvisionContext) -> StepResult:
    return _ok(
        'voice_binding',
        f"piper={ctx.agent.voice.piper_voice} verified={ctx.agent.voice.onnx_verified}",
        deferred=not ctx.agent.voice.onnx_verified,
    )


def _step_room(ctx: ProvisionContext) -> StepResult:
    if not ctx.agent.room or not ctx.agent.room.route:
        return StepResult('room_ownership', 'failed', 'room.route required')
    return _ok('room_ownership', ctx.agent.room.route)


def _step_discord(ctx: ProvisionContext) -> StepResult:
    return _ok('discord_routing', 'optional; not configured', deferred=True)


def _step_decision(ctx: ProvisionContext) -> StepResult:
    return _ok('decision_domain_registration', ctx.agent.domain, deferred=True)


STEP_HANDLERS: dict[str, StepHandler] = {
    'roster_registration': _step_roster,
    'stable_agent_id': _step_id,
    'persona_storage': _step_persona,
    'role_domain_assignment': _step_role,
    'hierarchy_placement': _step_hierarchy,
    'greeting_fast_path': _step_greeting,
    'voice_binding': _step_voice,
    'motion_manifest': _step_motion,
    'emotional_state_init': _step_emotion,
    'relationship_graph_init': _step_relationships,
    'dossier_init': _step_dossier,
    'journal_init': _step_journal,
    'room_ownership': _step_room,
    'discord_routing': _step_discord,
    'decision_domain_registration': _step_decision,
}


def _tx_path(layout: StateLayout, tx_id: str) -> Path:
    return layout.user_agents / 'provision' / f'{tx_id}.json'


def save_transaction(tx: ProvisionTransaction, layout: StateLayout) -> Path:
    path = _tx_path(layout, tx.tx_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(tx), indent=2, default=str) + '\n', encoding='utf-8')
    return path


def load_transaction(tx_id: str, layout: Optional[StateLayout] = None) -> ProvisionTransaction:
    layout = layout or resolve_layout()
    data = json.loads(_tx_path(layout, tx_id).read_text(encoding='utf-8'))
    return ProvisionTransaction(**{k: data[k] for k in ProvisionTransaction.__dataclass_fields__ if k in data})


def provision_agent(
    agent: Agent,
    *,
    layout: Optional[StateLayout] = None,
    bus: Optional[EventBus] = None,
    persist_agent: bool = True,
) -> ProvisionTransaction:
    """Run the 15-step provisioning transaction for one agent."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    bus = bus or EventBus(layout=layout, persist=True)
    now = time.time()
    tx = ProvisionTransaction(
        tx_id=f'tx_{uuid.uuid4().hex[:12]}',
        agent_id=agent.agent_id,
        status=ProvisionStatus.IN_PROGRESS.value,
        created_at=now,
        updated_at=now,
        agent_snapshot=agent_to_dict(agent),
    )
    ctx = ProvisionContext(layout=layout, agent=agent, tx=tx, bus=bus)
    bus.emit(new_event(
        'provision.started',
        actor='system',
        subject=agent.agent_id,
        payload={'tx_id': tx.tx_id},
        correlation_id=tx.tx_id,
    ))

    completed_steps: list[str] = []
    try:
        for step in PROVISION_STEPS:
            handler = STEP_HANDLERS[step]
            result = handler(ctx)
            tx.steps.append(asdict(result))
            tx.updated_at = time.time()
            bus.emit(new_event(
                'provision.step',
                actor='system',
                subject=agent.agent_id,
                payload=asdict(result),
                correlation_id=tx.tx_id,
            ))
            if result.status != 'completed':
                tx.status = ProvisionStatus.RESUMABLE.value
                tx.error = result.detail
                save_transaction(tx, layout)
                bus.emit(new_event(
                    'provision.failed',
                    actor='system',
                    subject=agent.agent_id,
                    payload={'tx_id': tx.tx_id, 'step': step, 'error': result.detail},
                    correlation_id=tx.tx_id,
                ))
                return tx
            completed_steps.append(step)

        if persist_agent:
            out = layout.user_agents / f'default-{agent.agent_id}.json'
            # Preserve created_at on re-provision (compat with seed_defaults)
            if out.exists():
                try:
                    existing = json.loads(out.read_text(encoding='utf-8'))
                    if existing.get('created_at'):
                        agent.created_at = existing['created_at']
                except (json.JSONDecodeError, OSError):
                    pass
            agent.updated_at = time.time()
            out.write_text(
                json.dumps(agent_to_dict(agent), indent=2, default=str) + '\n',
                encoding='utf-8',
            )

        tx.status = ProvisionStatus.COMPLETED.value
        tx.updated_at = time.time()
        save_transaction(tx, layout)
        bus.emit(new_event(
            'provision.completed',
            actor='system',
            subject=agent.agent_id,
            payload={'tx_id': tx.tx_id, 'steps': completed_steps},
            correlation_id=tx.tx_id,
        ))
        return tx
    except Exception as exc:  # noqa: BLE001
        tx.status = ProvisionStatus.FAILED.value
        tx.error = str(exc)
        tx.updated_at = time.time()
        save_transaction(tx, layout)
        bus.emit(new_event(
            'provision.failed',
            actor='system',
            subject=agent.agent_id,
            payload={'tx_id': tx.tx_id, 'error': str(exc)},
            correlation_id=tx.tx_id,
        ))
        raise


def provision_default_roster(layout: Optional[StateLayout] = None) -> list[ProvisionTransaction]:
    from expansion.seed_defaults import build_default_roster
    layout = layout or resolve_layout()
    bus = EventBus(layout=layout, persist=True)
    return [provision_agent(a, layout=layout, bus=bus) for a in build_default_roster()]
