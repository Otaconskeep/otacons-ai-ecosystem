# -*- coding: utf-8 -*-
"""Premium side of differential harness."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from expansion.hermes.behavioral_policy import classify_behavioral_intent, resolve_agent_id
from expansion.hermes.behavior_pipeline import run_full_turn_without_llm
from expansion.state_layout import resolve_layout


class PremiumSession:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix='premium_parity_'))
        cfg = self.root / 'cfg'
        data = self.root / 'data'
        cfg.mkdir(parents=True, exist_ok=True)
        data.mkdir(parents=True, exist_ok=True)
        os.environ['OTACON_EXPANSION_CONFIG_ROOT'] = str(cfg)
        os.environ['OTACON_EXPANSION_DATA_ROOT'] = str(data)
        os.environ['HERMES_PERSONALITY_RUNTIME_ENABLED'] = 'true'
        self.layout = resolve_layout()

    def apply_message(self, message: str, agent: str = 'AGENT_A') -> dict:
        aid = resolve_agent_id(agent)
        # Seed formula9 corpus via reflections
        from expansion.continuity.memory_engine import MemoryEngine, score_and_rank
        MemoryEngine.write_reflection(
            aid, trigger='seed', note='PROJECT_ALPHA research plan failed on routers',
            emotional_weight='negative', layout=self.layout,
        )
        MemoryEngine.write_reflection(
            aid, trigger='seed', note='casual weather chat with USER_PRIMARY',
            emotional_weight='neutral', layout=self.layout,
        )
        MemoryEngine.write_reflection(
            aid, trigger='seed', note='coding success on AGENT_A helper script',
            emotional_weight='positive', layout=self.layout,
        )

        turn = run_full_turn_without_llm(aid, message, layout=self.layout)
        pre = turn.get('pre') or {}
        policy = turn.get('behavioral_policy') or {}

        corpus = [
            {'id': 'm1', 'note': 'PROJECT_ALPHA research plan failed on routers', 'sentiment': 'negative'},
            {'id': 'm2', 'note': 'casual weather chat with USER_PRIMARY', 'sentiment': 'neutral'},
            {'id': 'm3', 'note': 'coding success on AGENT_A helper script', 'sentiment': 'positive'},
            {'id': 'm4', 'note': 'USER_PRIMARY praised AGENT_A for great work', 'sentiment': 'positive'},
            {'id': 'm5', 'note': 'stale memory about unrelated hobby', 'sentiment': 'neutral'},
        ]
        terms = [t for t in (message or '').lower().split() if len(t) > 3][:8]
        ranked = score_and_rank(corpus, terms or ['project'], aid, top_k=3)

        return {
            'system': 'premium',
            'entity_id': aid,
            'intent': policy.get('intent') or classify_behavioral_intent(message),
            'behavioral_policy': policy,
            'emotion_before': pre.get('emotion_before'),
            'emotion_after': pre.get('emotion_after'),
            'emotion_delta': pre.get('emotion_delta'),
            'mood_before': (pre.get('emotion_before') or {}).get('mood'),
            'mood_after': (pre.get('emotion_after') or {}).get('mood'),
            'relationship_before': pre.get('relationship_before'),
            'relationship_after': pre.get('relationship_after'),
            'relationship_delta': pre.get('relationship_delta'),
            'formula9_top_ids': [r.get('id') for r in ranked],
            'formula9_top_scores': [r.get('_formula9_score') for r in ranked],
            'text': turn.get('text'),
            'ok': turn.get('ok'),
            'layers_failed': pre.get('layers_failed') or [],
            'state_event': policy.get('state_event'),
        }
