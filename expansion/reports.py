"""Agent Reports — real runtime state, not cosmetic cards."""
from __future__ import annotations

from typing import Optional

from expansion.canonical_dossiers import get_canonical_dossier
from expansion.diary import DiaryStore
from expansion.emotion_store import EmotionStore
from expansion.jobs import JobStore
from expansion.journal import JournalStore
from expansion.living_dossier import LivingDossierStore
from expansion.relationship_interpret import RelationshipInterpreter
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import StateLayout, resolve_layout
from expansion.vulnerability_runtime import VulnerabilityRuntime


def build_agent_report(agent_id: str, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    rt = ExpansionRuntime(layout)
    view = rt.get_agent(agent_id)
    if view is None:
        raise KeyError(agent_id)
    dossier = get_canonical_dossier(agent_id)
    emo = EmotionStore(layout).get_or_create(agent_id)
    jobs = JobStore(layout)
    active = jobs.list(agent_id=agent_id, limit=20)
    active_open = [j for j in active if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')]
    completed = [j for j in jobs.list(agent_id=agent_id, limit=50) if j.status == 'COMPLETE']
    failed = [j for j in jobs.list(agent_id=agent_id, limit=50) if j.status == 'FAILED']
    total_done = len(completed) + len(failed)
    success_rate = (len(completed) / total_done) if total_done else None
    journals = JournalStore(layout).recent(agent_id=agent_id, limit=5)
    diaries = DiaryStore(layout).recent(agent_id, limit=3)
    living = LivingDossierStore(layout).load(agent_id)
    rels = RelationshipInterpreter(layout)
    highlights = [
        rels.summarize(agent_id, other)
        for other in ('user_primary', 'aria', 'muse', 'ledger', 'vector', 'sentry')
        if other != agent_id
    ][:4]
    vulns = VulnerabilityRuntime(layout).apply_decay(agent_id)
    return {
        'agent_id': agent_id,
        'display_name': view.display_name,
        'role': view.role,
        'archetype': dossier.character.archetype,
        'runtime_status': 'active' if view else 'unknown',
        'emotion': {k: round(v, 4) for k, v in emo.dimensions.items()},
        'emotion_why': {
            'jealousy': emo.explain('jealousy'),
            'stress': emo.explain('stress'),
            'concern': emo.explain('concern'),
            'confidence': emo.explain('confidence'),
        },
        'active_jobs': [j.__dict__ for j in active_open],
        'recent_completed_jobs': [j.__dict__ for j in completed[:5]],
        'metrics': {
            'completed': len(completed),
            'failed': len(failed),
            'success_rate': success_rate,
        },
        'relationship_highlights': [
            {
                'target': h.target_id,
                'label': h.label,
                'narrative': h.narrative,
                'dimensions': h.dimensions,
            }
            for h in highlights
        ],
        'recent_journal': [
            {
                'entry_id': e.entry_id,
                'summary': e.summary,
                'timestamp': e.timestamp,
                'event_ids': list(e.event_ids),
            }
            for e in journals
        ],
        'latest_diary': diaries[0] if diaries else None,
        'recent_diary': diaries[:5],
        'living_observations': [o.__dict__ if hasattr(o, '__dict__') else o for o in living.observations[:10]],
        'vulnerability_activations': vulns.activations,
        'capabilities': {
            'voice': view.voice_id,
            'room': view.room_route,
            'motion_manifest': view.motion_manifest_id,
            'strengths': list(dossier.capabilities.strengths or ()),
            'weaknesses': list(dossier.capabilities.weaknesses or ()) if not isinstance(dossier.capabilities.weaknesses, str) else [dossier.capabilities.weaknesses],
        },
        'diary_style': dossier.character.diary_style,
        'social': {
            'attachment_style': dossier.social.attachment_style,
            'jealousy_sensitivity': dossier.social.jealousy_sensitivity,
            'rivalry_behavior': dossier.social.rivalry_behavior,
        },
    }
