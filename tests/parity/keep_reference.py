# -*- coding: utf-8 -*-
"""Keep reference adapter — isolated synthetic OTACON_DATA_DIR only.

NEVER points at live Keep data. Uses AGENT_A / USER_PRIMARY fixtures.
Imports real Keep continuity formula engines for differential comparison.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _keep_root() -> Path:
    raw = (
        os.environ.get('KEEP_REFERENCE_ROOT')
        or os.environ.get('OTACON_KEEP_REFERENCE_ROOT')
        or ''
    )
    return Path(raw) if raw else Path.cwd()


_MSG_TO_STATE_EVENT = {
    'critique': 'user_mild_criticism',
    'hostility': 'user_hostility',
    'praise': 'user_praise',
    'gratitude': 'user_gratitude',
    'apology': 'user_apology',
    'ask': 'operator_ask',
    'ask_subjective': 'operator_ask_subjective',
}

_MSG_TO_F5_EVENT = {
    'critique': 'operator_ask',
    'hostility': 'social_reply_disagree',
    'praise': 'operator_ask_subjective',
    'gratitude': 'operator_ask_subjective',
    'apology': 'operator_ask_subjective',
    'ask': 'operator_ask',
    'ask_subjective': 'operator_ask_subjective',
}


def _classify_bucket(message: str) -> str:
    m = (message or '').lower()
    if any(p in m for p in (
        'thank', 'great work', 'good job', 'amazing', 'awesome', 'proud',
        'well done', 'brilliant', 'perfect', 'appreciate', 'excellent',
        'love working', 'nice work',
    )):
        return 'praise'
    if any(p in m for p in (
        'you suck', 'useless', 'hate you', 'hate this', 'garbage', 'idiot',
        'shut up', 'worst', 'being lazy',
    )):
        return 'hostility'
    if any(p in m for p in (
        "didn't work", 'did not work', 'you missed', 'wrong', 'failed', 'not working',
        'messed up', 'messed this up', 'not good enough', 'try again', 'do better', 'incorrect',
        'not what i', 'why did that break', 'still broken', 'missed the', 'fix it',
        'please fix', 'regression',
    )):
        return 'critique'
    if any(p in m for p in ("i'm sorry", 'i am sorry', 'apologize', 'my bad')):
        return 'apology'
    if any(p in m for p in ('feel', 'miss you', 'lonely')):
        return 'ask_subjective'
    return 'ask'


class KeepReferenceSession:
    """Isolated Keep formula sandbox for one differential run."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix='keep_ref_synth_'))
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'continuity' / 'registries').mkdir(parents=True, exist_ok=True)
        (self.root / 'continuity' / 'memory' / 'agent_a').mkdir(parents=True, exist_ok=True)
        (self.root / 'agent_states.json').write_text('{}', encoding='utf-8')
        (self.root / 'personnel_relationships.json').write_text(
            json.dumps({'reporting': {}, 'relationships': [], 'psych_profiles': {}}),
            encoding='utf-8',
        )
        (self.root / 'genome_entities.json').write_text(
            json.dumps({
                'entities': {
                    'agent_a': {
                        'display_name': 'AGENT_A',
                        'identity': {'role': 'coordinator'},
                    }
                }
            }),
            encoding='utf-8',
        )
        self._prepare_import()

    def _prepare_import(self) -> None:
        os.environ['OTACON_DATA_DIR'] = str(self.root)
        os.environ['DATA_DIR'] = str(self.root)
        for m in list(sys.modules):
            if m == 'continuity' or m.startswith('continuity.'):
                del sys.modules[m]
        keep_root = str(_keep_root())
        if keep_root not in sys.path:
            sys.path.insert(0, keep_root)
    def snapshot_state(self, entity_id: str = 'agent_a') -> dict:
        from continuity.state_engine import StateEngine
        s = StateEngine.get(entity_id)
        return {
            'mood': s.get('mood'),
            'happiness': float(s.get('happiness', 0.55)),
            'confidence': float(s.get('confidence', 0.55)),
            'energy': float(s.get('energy', 0.60)),
            'residue': float(s.get('_residue', 0.0)),
        }

    def snapshot_rel(self, frm: str = 'agent_a', to: str = 'user_primary') -> dict:
        from continuity.relationship import RelationshipEngine
        return {
            'ally': float(RelationshipEngine.strength(frm, to, 'ally')),
            'colleague': float(RelationshipEngine.strength(frm, to, 'colleague')),
        }

    def apply_message(self, message: str, entity_id: str = 'agent_a') -> dict:
        """Apply Keep StateEngine + RelationshipEngine for synthetic message."""
        from continuity.state_engine import StateEngine
        from continuity.relationship import RelationshipEngine
        from continuity.memory_engine import score_memory_entry

        bucket = _classify_bucket(message)
        state_event = _MSG_TO_STATE_EVENT[bucket]
        f5_event = _MSG_TO_F5_EVENT[bucket]

        before = self.snapshot_state(entity_id)
        rel_before = self.snapshot_rel(entity_id)

        StateEngine.update_from_event(entity_id, state_event)
        RelationshipEngine.update_on_event(entity_id, 'user_primary', f5_event)

        # Do NOT call Keep MemoryEngine writers — MEMORY_DIR is host-coupled.
        # Formula 9 comparison uses the shared synthetic corpus only.

        after = self.snapshot_state(entity_id)
        rel_after = self.snapshot_rel(entity_id)

        # Formula 9 rank synthetic corpus
        corpus = [
            {'id': 'm1', 'note': 'PROJECT_ALPHA research plan failed on routers', 'sentiment': 'negative'},
            {'id': 'm2', 'note': 'casual weather chat with USER_PRIMARY', 'sentiment': 'neutral'},
            {'id': 'm3', 'note': 'coding success on AGENT_A helper script', 'sentiment': 'positive'},
            {'id': 'm4', 'note': 'USER_PRIMARY praised AGENT_A for great work', 'sentiment': 'positive'},
            {'id': 'm5', 'note': 'stale memory about unrelated hobby', 'sentiment': 'neutral'},
        ]
        terms = [t for t in (message or '').lower().split() if len(t) > 3][:8]
        scored = []
        for rank, entry in enumerate(corpus):
            s = score_memory_entry(entry, terms or ['project'], entity_id, rank, set())
            scored.append((s, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [e for _, e in scored[:3]]
        top_scores = [s for s, _ in scored[:3]]

        return {
            'system': 'keep_reference',
            'entity_id': entity_id,
            'bucket': bucket,
            'state_event': state_event,
            'f5_event': f5_event,
            'emotion_before': before,
            'emotion_after': after,
            'emotion_delta': {
                k: round(after[k] - before[k], 4)
                for k in ('happiness', 'confidence', 'energy', 'residue')
            },
            'mood_before': before['mood'],
            'mood_after': after['mood'],
            'relationship_before': rel_before,
            'relationship_after': rel_after,
            'relationship_delta': {
                'ally': round(rel_after['ally'] - rel_before['ally'], 4),
                'colleague': round(rel_after['colleague'] - rel_before['colleague'], 4),
            },
            'formula9_top_ids': [r.get('id') for r in ranked],
            'formula9_top_scores': top_scores,
        }
