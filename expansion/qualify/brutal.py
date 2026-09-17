"""Brutal state-survival scenario helpers (release gate)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.diary import DiaryStore
from expansion.emotion_store import EmotionStore
from expansion.events import new_event
from expansion.jobs import JobStore
from expansion.journal import JournalStore
from expansion.living_dossier import LivingDossierStore
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.pipeline import LivingPipeline
from expansion.relationship_store import RelationshipStore
from expansion.rooms import RoomRegistry
from expansion.state_layout import StateLayout, resolve_layout


AGENTS = ('aria', 'vector', 'ledger', 'muse', 'sentry')


@dataclass
class StateSnapshot:
    owner_prefs: dict
    memories: dict
    relationships: dict
    emotions: dict
    emotion_provenance_lens: dict
    journals: dict
    diaries: dict
    living: dict
    jobs: dict
    rooms: int

    def to_dict(self) -> dict:
        return asdict(self)


def populate_rich_state(layout: Optional[StateLayout] = None) -> StateSnapshot:
    """Create the full brutal-test user state via real events/APIs."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    pipe = LivingPipeline(layout)
    mem = ExpansionMemory(layout)

    # Owner identity / prefs
    prefs = layout.user_preferences / 'owner.json'
    owner = {'display_name': 'Owner', 'id': 'user_primary', 'locale': 'en'}
    prefs.write_text(json.dumps(owner, indent=2) + '\n', encoding='utf-8')

    for aid in AGENTS:
        mem.add(new_memory(
            aid, f'Owner activated Keep with {aid} present.',
            kind='episodic', source='brutal_test', importance=0.8,
        ))

    # Relationship + emotion via real events
    for _ in range(3):
        pipe.apply_event(new_event(
            'user.praised_agent', actor='user', subject='muse',
            payload={'text': 'great work'},
        ))
    pipe.apply_event(new_event(
        'user.praised_agent', actor='user', subject='aria',
        payload={'reassure': True, 'text': 'still need you'},
    ))
    for i in range(2):
        pipe.create_and_run_job(f'infra task {i}', domain='infrastructure', succeed=True)
    pipe.create_and_run_job('failed probe', domain='systems', succeed=False, error='timeout')
    pipe.create_and_run_job('security sweep', domain='security', succeed=True)
    # Leave one active job
    JobStore(layout).create('active watch', domain='monitoring')

    RoomRegistry(layout).seed_defaults()
    return capture_state(layout)


def capture_state(layout: Optional[StateLayout] = None) -> StateSnapshot:
    layout = layout or resolve_layout()
    emo = EmotionStore(layout)
    rels = RelationshipStore(layout)
    journals = JournalStore(layout)
    diaries = DiaryStore(layout)
    living = LivingDossierStore(layout)
    jobs = JobStore(layout)
    mem = ExpansionMemory(layout)

    owner = {}
    op = layout.user_preferences / 'owner.json'
    if op.is_file():
        owner = json.loads(op.read_text(encoding='utf-8'))

    memories = {a: [m.content for m in mem.list(a)[:20]] for a in AGENTS}
    relationships = {}
    for src, dst in (('aria', 'muse'), ('aria', 'vector'), ('muse', 'aria')):
        r = rels.get(src, dst)
        relationships[f'{src}->{dst}'] = {
            'dimensions': dict(r.dimensions) if r else {},
            'provenance': list(r.provenance_event_ids[-10:]) if r else [],
        }
    emotions = {}
    emotion_prov = {}
    for a in AGENTS:
        e = emo.get(a)
        emotions[a] = dict(e.dimensions) if e else {}
        emotion_prov[a] = len(e.provenance) if e else 0
    jn = {a: [x.entry_id for x in journals.recent(agent_id=a, limit=50)] for a in AGENTS}
    dy = {a: [d.get('diary_id') for d in diaries.recent(a, limit=50)] for a in AGENTS}
    lv = {
        a: [(o.observation_id, o.category, o.value) for o in living.load(a).observations]
        for a in AGENTS
    }
    jb = {
        'ids': [j.job_id for j in jobs.list(limit=100)],
        'statuses': sorted({j.status for j in jobs.list(limit=100)}),
    }
    rooms = len(RoomRegistry(layout).list())
    return StateSnapshot(
        owner_prefs=owner,
        memories=memories,
        relationships=relationships,
        emotions=emotions,
        emotion_provenance_lens=emotion_prov,
        journals=jn,
        diaries=dy,
        living=lv,
        jobs=jb,
        rooms=rooms,
    )


def diff_states(before: StateSnapshot, after: StateSnapshot) -> list:
    """Return human-readable mismatches (empty = exact survival)."""
    mismatches = []
    b, a = before.to_dict(), after.to_dict()
    for key in b:
        if b[key] != a[key]:
            mismatches.append(f'{key} changed')
    return mismatches
