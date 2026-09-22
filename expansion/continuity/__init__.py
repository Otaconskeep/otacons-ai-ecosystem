# -*- coding: utf-8 -*-
"""Public Expansion continuity package — clean-room Keep-parity layers.

Formulas: 4 (state), 5 (relationship), 7 (residue), 8 (mood), 9 (memory).
Hermes behavioral pipeline owns pre-LLM decisions.
No private Keep data, LAN topology, or third-party IP roster names.
"""
from expansion.continuity.emotion_bridge import (
    formula_catalog,
    formula8_score,
    get_emotion_vector,
    normalize_vector,
)
from expansion.continuity.state_engine import StateEngine
from expansion.continuity.relationship import RelationshipEngine
from expansion.continuity.memory_engine import MemoryEngine, score_memory_entry
from expansion.continuity.preferences import PreferenceStore
from expansion.continuity.health import snapshot as continuity_health

__all__ = [
    'StateEngine',
    'RelationshipEngine',
    'MemoryEngine',
    'PreferenceStore',
    'continuity_health',
    'formula_catalog',
    'formula8_score',
    'get_emotion_vector',
    'normalize_vector',
    'score_memory_entry',
]
