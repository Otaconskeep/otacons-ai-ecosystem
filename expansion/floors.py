"""Aggregated floor payloads for flagship Expansion UI — real store data only."""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from expansion.canonical_dossiers import CANONICAL_AGENT_IDS, get_canonical_dossier
from expansion.diary import DiaryStore
from expansion.emotion import EMOTION_DIMENSIONS
from expansion.emotion_store import EmotionStore
from expansion.events import EventBus
from expansion.jobs import JobStore
from expansion.journal import JournalStore
from expansion.learning import LearningEngine
from expansion.living_dossier import LivingDossierStore
from expansion.memory_bridge import ExpansionMemory
from expansion.readiness import evaluate_foundation
from expansion.relationship_interpret import RelationshipInterpreter
from expansion.rex import build_rex_board, HARD_BLOCK_STAGE
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import StateLayout, resolve_layout
from expansion.tools import ToolGateway

DEPTH_KINDS = (
    'fear', 'anxiety', 'insecurity', 'self_conscious', 'self_conscious_area',
    'weakness', 'crutch', 'compulsion', 'addictive_tendency',
)


def _vuln_item(v) -> dict:
    return {
        'kind': v.kind,
        'label': v.label,
        'intensity': v.intensity,
        'description': v.description,
        'triggers': list(v.triggers or ()),
        'affects_operations': bool(v.affects_operations),
        'intentional_absence': bool(getattr(v, 'intentional_absence', False)),
    }


def group_vulnerabilities(items) -> dict:
    by_kind = {k: [] for k in DEPTH_KINDS}
    by_kind['other'] = []
    for raw in items or ():
        row = _vuln_item(raw) if hasattr(raw, 'kind') else dict(raw)
        kind = row.get('kind') or 'other'
        if kind in by_kind:
            by_kind[kind].append(row)
        elif kind == 'self_conscious_area':
            by_kind['self_conscious'].append(row)
        else:
            by_kind['other'].append(row)
    return by_kind


def build_dossier_card(agent_id: str, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    d = get_canonical_dossier(agent_id, layout)
    living = LivingDossierStore(layout).load(agent_id)
    learn = LearningEngine(layout).agent_learning_surface(agent_id)
    interp = RelationshipInterpreter(layout)
    emo = EmotionStore(layout).get_or_create(agent_id)
    rel_highlights = []
    for other in CANONICAL_AGENT_IDS:
        if other == agent_id:
            continue
        s = interp.summarize(agent_id, other)
        rel_highlights.append({
            'target': other,
            'label': s.label,
            'narrative': s.narrative,
            'dimensions': s.dimensions,
        })
    caps = d.capabilities
    strengths = list(caps.strengths) if isinstance(caps.strengths, (list, tuple)) else [caps.strengths]
    weaknesses = list(caps.weaknesses) if isinstance(caps.weaknesses, (list, tuple)) else [caps.weaknesses]
    return {
        'agent_id': agent_id,
        'identity': asdict(d.identity),
        'background': asdict(d.background),
        'character': asdict(d.character),
        'capabilities': {
            'strengths': [x for x in strengths if x],
            'weaknesses': [x for x in weaknesses if x],
            'blind_spots': caps.blind_spots if isinstance(caps.blind_spots, (list, tuple)) else [caps.blind_spots],
            'failure_modes': caps.failure_modes if isinstance(caps.failure_modes, (list, tuple)) else [caps.failure_modes],
        },
        'social': asdict(d.social),
        'stress': asdict(d.stress),
        'preferences': asdict(d.preferences),
        'vulnerabilities': {
            'items': [_vuln_item(v) for v in d.vulnerabilities.items],
            'by_kind': group_vulnerabilities(d.vulnerabilities.items),
        },
        'emotional_baseline': dict(d.stress.emotional_baseline or {}),
        'current_emotion': {k: round(v, 4) for k, v in emo.dimensions.items()},
        'living': {
            'observations': [asdict(o) for o in living.observations[:40]],
            'notes': living.notes,
        },
        'learning': learn,
        'relationship_highlights': rel_highlights,
        'canonical_history_notes': d.canonical_history_notes,
    }


def build_dossiers_index(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    return {
        'surface': 'dossiers',
        'agents': [build_dossier_card(aid, layout) for aid in CANONICAL_AGENT_IDS],
        'rule': 'Canonical = product lore; living = observed with evidence; learning ≠ dossier.',
    }


def build_dashboard(layout: Optional[StateLayout] = None) -> dict:
    """Command Center owner overview — distinct from Aria Command floor."""
    layout = layout or resolve_layout()
    rt = ExpansionRuntime(layout)
    if not rt.expansion_enabled():
        return {'enabled': False}
    jobs = JobStore(layout)
    emo = EmotionStore(layout)
    interp = RelationshipInterpreter(layout)
    learn = LearningEngine(layout)
    bus = EventBus(persist=True)
    board = build_rex_board(layout)
    roster = []
    for a in rt.load_roster():
        e = emo.get_or_create(a.agent_id)
        top = sorted(e.dimensions.items(), key=lambda kv: kv[1], reverse=True)[:5]
        roster.append({
            'agent_id': a.agent_id,
            'display_name': a.display_name,
            'role': a.role,
            'emotion': {k: round(v, 3) for k, v in top},
            'baseline': {k: round(float(v), 3) for k, v in (e.baseline or {}).items()},
        })
    active = [asdict(j) for j in jobs.list(limit=40)
              if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')]
    alerts = [asdict(j) for j in jobs.list(status='FAILED', limit=12)]
    shifts = []
    for edge in (('aria', 'muse'), ('muse', 'aria'), ('aria', 'vector'), ('ledger', 'aria')):
        s = interp.summarize(*edge)
        shifts.append({
            'source': s.source_id, 'target': s.target_id,
            'label': s.label, 'narrative': s.narrative, 'dimensions': s.dimensions,
        })
    shared = learn.board_payload().get('shared_keep') or []
    return {
        'enabled': True,
        'surface': 'command_center',
        'owner': {'id': 'user_primary', 'label': 'Owner'},
        'system_status': {
            'foundation': evaluate_foundation(layout).to_dict(),
            'rex_metrics': board.get('metrics') or {},
        },
        'roster': roster,
        'active_autonomous_jobs': active[:20],
        'alerts': alerts,
        'recent_events': [
            {'event_id': e.event_id, 'event_type': e.event_type,
             'actor': e.actor, 'subject': e.subject, 'timestamp': e.timestamp}
            for e in bus.recent(limit=20)
        ],
        'relationship_shifts': shifts,
        'learning_highlights': shared[:8],
        'package_readiness': evaluate_foundation(layout).to_dict(),
        'note': 'Dashboard = owner overview. Aria Command = coordination floor.',
    }


def build_war_room(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    jobs = JobStore(layout)
    board = build_rex_board(layout)
    all_jobs = jobs.list(limit=80)
    by_status = {
        'active': [asdict(j) for j in all_jobs if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING')],
        'waiting_verify': [asdict(j) for j in all_jobs if j.status == 'WAITING'],
        'blocked': [asdict(j) for j in all_jobs if j.status == 'BLOCKED'],
        'failed': [asdict(j) for j in all_jobs if j.status == 'FAILED'],
        'complete': [asdict(j) for j in all_jobs if j.status == 'COMPLETE'][:15],
    }
    columns = {c['status']: c for c in (board.get('columns') or [])}
    return {
        'surface': 'war_room',
        'owner': 'vector',
        'commander': 'aria',
        'operations': by_status,
        'rex': {
            'metrics': board.get('metrics') or {},
            'verifying': columns.get('VERIFYING'),
            'rework': columns.get('REWORK'),
            'hard_blocked': columns.get(HARD_BLOCK_STAGE) or columns.get('HARD_BLOCKED'),
            'peer_review_note': (
                'VERIFYING includes mandatory cross-agent peer review before DONE.'
            ),
        },
        'incidents': by_status['failed'][:15] + by_status['blocked'][:10],
        'recovery': {
            'rework_cards': (columns.get('REWORK') or {}).get('cards') or [],
            'retrying': [asdict(j) for j in all_jobs if j.status == 'FAILED'][:10],
        },
        'decision_trace': [
            {
                'job_id': j.job_id,
                'status': j.status,
                'assigned_agent': j.assigned_agent,
                'evidence': list(j.evidence or ()),
                'error': j.error,
                'request': j.request,
            }
            for j in all_jobs[:25]
        ],
        'peer_review_note': (
            'VERIFYING includes mandatory cross-agent peer review before DONE.'
        ),
        # Legacy aliases for thin clients
        'active': by_status['active'] + by_status['waiting_verify'] + by_status['blocked'],
        'failed': by_status['failed'],
        'complete': by_status['complete'],
        'note': 'War Room = operational command; links into Project REX jobs.',
    }


def build_command_floor(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    rt = ExpansionRuntime(layout)
    jobs = JobStore(layout)
    emo = EmotionStore(layout)
    interp = RelationshipInterpreter(layout)
    board = build_rex_board(layout)
    roster = []
    workload = {}
    for a in rt.load_roster():
        e = emo.get_or_create(a.agent_id)
        top = sorted(e.dimensions.items(), key=lambda kv: kv[1], reverse=True)[:4]
        open_jobs = [j for j in jobs.list(agent_id=a.agent_id, limit=30)
                     if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')]
        workload[a.agent_id] = len(open_jobs)
        roster.append({
            'agent_id': a.agent_id,
            'display_name': a.display_name,
            'role': a.role,
            'emotion_highlights': {k: round(v, 3) for k, v in top},
            'open_jobs': len(open_jobs),
        })
    shifts = []
    for edge in (('aria', 'muse'), ('aria', 'vector'), ('muse', 'aria'), ('ledger', 'muse')):
        s = interp.summarize(*edge)
        if s.label in ('competitive_attachment', 'jealous_attachment', 'strained', 'devoted'):
            shifts.append({
                'source': s.source_id, 'target': s.target_id,
                'label': s.label, 'narrative': s.narrative,
            })
    return {
        'surface': 'aria_command_floor',
        'note': 'Aria Command = agent coordination; Dashboard = owner overview.',
        'roster': roster,
        'workload': workload,
        'active_jobs': [asdict(j) for j in jobs.list(limit=30)
                        if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')],
        'delegations': [
            {'job_id': j.job_id, 'from': j.coordinator or 'aria', 'to': j.assigned_agent,
             'domain': j.domain, 'status': j.status, 'request': j.request}
            for j in jobs.list(limit=40)
            if j.assigned_agent
        ][:25],
        'readiness': evaluate_foundation(layout).to_dict(),
        'relationship_shifts': shifts,
        'emotion_shifts': shifts,
        'pending_decisions': (
            [asdict(j) for j in jobs.list(status='WAITING', limit=10)]
            + [asdict(j) for j in jobs.list(status='BLOCKED', limit=10)]
        ),
        'autonomous_summary': board.get('metrics') or {},
        'blockers': [
            c for col in (board.get('columns') or [])
            if col.get('status') in (HARD_BLOCK_STAGE, 'HARD_BLOCKED', 'REWORK')
            for c in (col.get('cards') or [])
        ][:15],
        'major_alerts': [asdict(j) for j in jobs.list(status='FAILED', limit=8)],
    }


def build_intel_floor(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    mem = ExpansionMemory(layout)
    important = []
    for aid in CANONICAL_AGENT_IDS:
        for m in mem.list(aid)[:20]:
            if m.importance >= 0.7:
                important.append({
                    'agent_id': aid, 'memory_id': m.memory_id,
                    'content': m.content, 'importance': m.importance,
                })
    living = {}
    store = LivingDossierStore(layout)
    for aid in CANONICAL_AGENT_IDS:
        doc = store.load(aid)
        living[aid] = [asdict(o) for o in doc.observations[:12]]
    learn = LearningEngine(layout).board_payload()
    return {
        'surface': 'ledger_intel',
        'important_memories': sorted(important, key=lambda x: -x['importance'])[:30],
        'journal_timeline': [asdict(e) for e in JournalStore(layout).recent(limit=50)],
        'living_dossiers': living,
        'learned_claims': {
            'shared': learn.get('shared_keep') or [],
            'private_by_agent': learn.get('private_by_agent') or {},
        },
        'relationship_evidence': RelationshipInterpreter(layout).matrix(
            list(CANONICAL_AGENT_IDS) + ['user_primary']
        ),
        'recent_events': [
            {'event_id': e.event_id, 'event_type': e.event_type,
             'actor': e.actor, 'subject': e.subject, 'timestamp': getattr(e, 'timestamp', 0)}
            for e in EventBus(persist=True).recent(limit=40)
        ],
        'continuity_search_hint': 'Filter client-side by agent, event_type, job_id, memory_id.',
        'note': 'No private medical/household data. Continuity = public Expansion history.',
    }


def build_ops_floor(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    from expansion.capabilities.home_assistant import probe_home_assistant
    from expansion.capabilities.discord_n8n import probe_discord, probe_n8n
    jobs = JobStore(layout)
    security = [j for j in jobs.list(agent_id='sentry', limit=60)
                if j.domain in ('security', 'monitoring') or j.assigned_agent == 'sentry']
    emo = EmotionStore(layout).get_or_create('sentry')
    tools = ToolGateway(layout).recent(limit=40)
    remediation = [t for t in tools if t.get('agent_id') == 'sentry' or 'security' in (t.get('capability') or '')]
    return {
        'surface': 'sentry_ops',
        'active_incidents': [asdict(j) for j in security if j.status in ('RUNNING', 'WAITING', 'BLOCKED', 'FAILED')][:20],
        'resolved_incidents': [asdict(j) for j in security if j.status == 'COMPLETE'][:15],
        'health_observations': {
            'emotion': {k: round(v, 3) for k, v in emo.dimensions.items()
                        if k in ('concern', 'fear', 'stress', 'confidence')},
            'emotion_why': {
                'concern': emo.explain('concern'),
                'fear': emo.explain('fear'),
            },
        },
        'security_findings': [asdict(j) for j in security][:25],
        'autonomous_remediation': remediation[:20],
        'monitoring_state': {
            'sentry_open_jobs': len([j for j in security if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING')]),
            'failed': len([j for j in security if j.status == 'FAILED']),
        },
        'service_readiness': {
            'home_assistant': probe_home_assistant().to_dict(),
            'discord': probe_discord().to_dict(),
            'n8n': probe_n8n().to_dict(),
        },
        'evidence': [
            {'job_id': j.job_id, 'evidence_ids': list(j.evidence or ()), 'error': j.error}
            for j in security[:20]
        ],
        'home_assistant': probe_home_assistant().to_dict(),
        'alerts': [asdict(j) for j in security if j.status == 'FAILED'][:20],
        'note': 'Home Assistant remains optional. HA UNAVAILABLE is not a product failure.',
    }


def build_emotion_roster(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    store = EmotionStore(layout)
    agents = []
    for aid in CANONICAL_AGENT_IDS:
        emo = store.get_or_create(aid)
        dossier = get_canonical_dossier(aid, layout)
        agents.append({
            'agent_id': aid,
            'display_name': dossier.identity.display_name,
            'dimensions': {k: round(float(emo.dimensions.get(k, 0)), 4) for k in EMOTION_DIMENSIONS},
            'baseline': {k: round(float((emo.baseline or {}).get(k, dossier.stress.emotional_baseline.get(k, 0.25))), 4)
                         for k in EMOTION_DIMENSIONS},
            'product_baseline': dict(dossier.stress.emotional_baseline or {}),
            'updated_at': emo.updated_at,
            'provenance_tail': list(emo.provenance or [])[-12:],
            'primary': sorted(emo.dimensions.items(), key=lambda kv: kv[1], reverse=True)[:5],
            'secondary': sorted(emo.dimensions.items(), key=lambda kv: kv[1], reverse=True)[5:10],
        })
    return {
        'surface': 'emotions',
        'agents': agents,
        'dimensions': list(EMOTION_DIMENSIONS),
        'rule': 'Runtime EmotionStore only — baselines from product + live decay/recovery.',
    }


def build_diary_index(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    store = DiaryStore(layout)
    agents = []
    for aid in CANONICAL_AGENT_IDS:
        rows = store.recent(aid, limit=40)
        d = get_canonical_dossier(aid, layout)
        agents.append({
            'agent_id': aid,
            'display_name': d.identity.display_name,
            'diary_style': d.character.diary_style,
            'count': len(rows),
            'latest': rows[0] if rows else None,
            'entries': rows,
        })
    return {
        'surface': 'diary',
        'agents': agents,
        'kind': 'diary',
        'rule': 'DIARY = WHAT IT MEANT (subjective). Journal = WHAT HAPPENED.',
    }


def build_journal_browser(layout: Optional[StateLayout] = None, agent_id: Optional[str] = None) -> dict:
    layout = layout or resolve_layout()
    entries = [asdict(e) for e in JournalStore(layout).recent(limit=100, agent_id=agent_id)]
    return {
        'surface': 'journal',
        'entries': entries,
        'agents': list(CANONICAL_AGENT_IDS),
        'kind': 'journal',
        'rule': 'JOURNAL = WHAT HAPPENED (objective).',
    }
