# -*- coding: utf-8 -*-
"""Emotion Bridge — Formula 4/7/8 + scale normalization for public Expansion.

Clean-room port of Keep continuity.emotion_bridge architecture.
Reads Expansion EmotionStore / RelationshipStore only.
Public agent IDs: aria, vector, ledger, muse, sentry.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

# Formula 4
_BASELINE = {'confidence': 0.55, 'happiness': 0.55, 'energy': 0.60}
_DECAY = 0.015

# Formula 7
_RESIDUE_DECAY = 0.88

# Formula 8
_EMO_W = {'happiness': 0.40, 'confidence': 0.35, 'energy': 0.15, 'residue': 0.10}

PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})

# Public aliases only — never Keep IP names
_ID_ALIASES = {
    'aria': 'aria',
    'agent_001': 'aria',
    'vector': 'vector',
    'ledger': 'ledger',
    'muse': 'muse',
    'sentry': 'sentry',
    'owner': 'user_primary',
    'user': 'user_primary',
    'user_primary': 'user_primary',
}

_lock = threading.Lock()


def canonical_entity_id(raw: str | None) -> str:
    s = (raw or '').strip().lower().replace('-', '_')
    if not s:
        return ''
    if s in _ID_ALIASES:
        return _ID_ALIASES[s]
    spaced = s.replace('_', ' ')
    if spaced in _ID_ALIASES:
        return _ID_ALIASES[spaced]
    return s.replace(' ', '_')


def _as_unit(value: Any, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if v > 1.0:
        v = v / 100.0
    return round(max(0.0, min(1.0, v)), 4)


def _as_residue(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if abs(v) > 1.0:
        v = max(-1.0, min(1.0, v / 100.0))
    return round(max(-1.0, min(1.0, v)), 4)


def derive_mood_label(
    happiness: float, confidence: float, energy: float, residue: float = 0.0,
) -> str:
    score = formula8_score(happiness, confidence, energy, residue)
    if score >= 0.72:
        return 'cheerful'
    if score >= 0.62:
        return 'pleased'
    if score >= 0.52:
        return 'focused' if energy >= 0.55 else 'neutral'
    if score >= 0.42:
        return 'brooding' if residue < -0.05 else 'neutral'
    if score >= 0.30:
        return 'anxious' if confidence < 0.45 else 'brooding'
    return 'volatile' if residue < -0.2 else 'detached'


def formula8_score(
    happiness: float, confidence: float, energy: float, residue: float = 0.0,
) -> float:
    return round(
        happiness * _EMO_W['happiness']
        + confidence * _EMO_W['confidence']
        + energy * _EMO_W['energy']
        + residue * _EMO_W['residue'],
        4,
    )


def normalize_vector(raw: dict | None, *, entity_id: str = '') -> dict:
    raw = raw if isinstance(raw, dict) else {}
    happiness = _as_unit(raw.get('happiness'), _BASELINE['happiness'])
    confidence = _as_unit(raw.get('confidence'), _BASELINE['confidence'])
    energy = _as_unit(raw.get('energy'), _BASELINE['energy'])
    residue = _as_residue(raw.get('_residue', raw.get('residue', 0.0)))
    stored_mood = str(raw.get('mood') or '').strip()
    formula8_mood = derive_mood_label(happiness, confidence, energy, residue)
    score = formula8_score(happiness, confidence, energy, residue)
    return {
        'entity_id': canonical_entity_id(entity_id) or None,
        'mood': formula8_mood,
        'mood_formula8': formula8_mood,
        'mood_stored': stored_mood or None,
        'happiness': happiness,
        'confidence': confidence,
        'energy': energy,
        'residue': residue,
        'is_stressed': residue < -0.25 or happiness <= 0.2 or formula8_mood in (
            'anxious', 'volatile', 'brooding', 'detached',
        ),
        'formula8_score': score,
        'updated': raw.get('_updated') or raw.get('updated_at'),
        'last_event': raw.get('last_event') or '',
        'raw_scale_detected': 'legacy_0_100' if any(
            _safe_float(raw.get(k)) > 1.0 for k in ('happiness', 'confidence', 'energy')
        ) else '0_1',
        'formula8_breakdown': {
            'happiness_term': round(happiness * _EMO_W['happiness'], 4),
            'confidence_term': round(confidence * _EMO_W['confidence'], 4),
            'energy_term': round(energy * _EMO_W['energy'], 4),
            'residue_term': round(residue * _EMO_W['residue'], 4),
            'weights': dict(_EMO_W),
        },
    }


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _dims_to_vector(dims: dict) -> dict:
    """Map Expansion 15-dim emotion → Formula 8 happiness/confidence/energy/residue."""
    joy = float(dims.get('joy', 0.35))
    satisfaction = float(dims.get('satisfaction', 0.4))
    pride = float(dims.get('pride', 0.35))
    sadness = float(dims.get('sadness', 0.15))
    stress = float(dims.get('stress', 0.15))
    anger = float(dims.get('anger', 0.1))
    confidence = float(dims.get('confidence', 0.55))
    curiosity = float(dims.get('curiosity', 0.45))
    frustration = float(dims.get('frustration', 0.15))
    loneliness = float(dims.get('loneliness', 0.2))
    happiness = max(0.0, min(1.0, 0.45 * joy + 0.30 * satisfaction + 0.15 * pride
                             - 0.25 * sadness - 0.15 * loneliness))
    energy = max(0.0, min(1.0, 0.55 * curiosity + 0.25 * (1.0 - stress)
                          + 0.20 * (1.0 - frustration)))
    residue = max(-1.0, min(1.0, 0.55 * anger + 0.35 * stress + 0.25 * frustration
                            - 0.35 * joy - 0.20 * satisfaction))
    return {
        'happiness': round(happiness, 4),
        'confidence': round(confidence, 4),
        'energy': round(energy, 4),
        'residue': round(residue, 4),
        '_updated': time.time(),
    }


def get_emotion_vector(
    entity_id: str,
    *,
    layout: Optional[StateLayout] = None,
) -> dict:
    canon = canonical_entity_id(entity_id)
    layout = layout or resolve_layout()
    raw: dict = {}
    try:
        from expansion.emotion_store import EmotionStore
        state = EmotionStore(layout).get(canon)
        if state is not None:
            raw = _dims_to_vector(state.dimensions or {})
            raw['updated_at'] = state.updated_at
            # Placeholder residue channel file (owner-local, never ships Keep data)
            residue_path = layout.user_data_root / 'emotion_residue' / f'{canon}.json'
            if residue_path.is_file():
                try:
                    extra = json.loads(residue_path.read_text(encoding='utf-8'))
                    if isinstance(extra, dict) and 'residue' in extra:
                        raw['residue'] = _as_residue(extra.get('residue'), raw['residue'])
                except Exception:
                    pass
    except Exception:
        raw = {}
    if not raw:
        # Mock resting baseline — not private Keep state
        raw = dict(_BASELINE)
        raw['residue'] = 0.0
        raw['_updated'] = time.time()
        raw['last_event'] = 'mock_baseline'
    vec = normalize_vector(raw, entity_id=canon)
    vec['state_found'] = bool(raw.get('last_event') != 'mock_baseline' or True)
    vec['state_key_resolved'] = canon
    return vec


def load_bond(
    entity_id: str,
    target_id: str = 'user_primary',
    *,
    layout: Optional[StateLayout] = None,
) -> dict:
    canon = canonical_entity_id(entity_id)
    tid = canonical_entity_id(target_id) or 'user_primary'
    layout = layout or resolve_layout()
    try:
        from expansion.relationship_store import RelationshipStore
        rel = RelationshipStore(layout).get(canon, tid)
        if rel is not None:
            dims = rel.dimensions if isinstance(rel.dimensions, dict) else {}
            return {
                'trust': float(dims.get('trust', 0.5)),
                'affection': float(dims.get('affinity', dims.get('affection', 0.5))),
                'bond_level': float(dims.get('attachment', 0.5)),
                'attachment': float(dims.get('attachment', 0.5)),
                'jealousy': float(dims.get('jealousy', 0.15)),
                'rivalry': float(dims.get('rivalry', 0.1)),
                'emotional_residue': {
                    'hurt': 0.0,
                    'concern': 0.0,
                    'warmth_surge': 0.0,
                    'pride': 0.0,
                },
            }
    except Exception:
        pass
    # Placeholder neutral bond — protects privacy; no owner history
    return {
        'trust': 0.55,
        'affection': 0.50,
        'bond_level': 0.50,
        'attachment': 0.50,
        'jealousy': 0.15,
        'rivalry': 0.10,
        'emotional_residue': {
            'hurt': 0.0, 'concern': 0.0, 'warmth_surge': 0.0, 'pride': 0.0,
        },
        '_placeholder': True,
    }


def apply_formula4_update(
    happiness: float, confidence: float, energy: float,
    *,
    dh: float = 0.0, dc: float = 0.0, de: float = 0.0,
) -> dict:
    """Formula 4: nudge + decay toward baseline."""
    h = happiness + dh - _DECAY * (happiness - _BASELINE['happiness'])
    c = confidence + dc - _DECAY * (confidence - _BASELINE['confidence'])
    e = energy + de - _DECAY * (energy - _BASELINE['energy'])
    return {
        'happiness': round(max(0.0, min(1.0, h)), 4),
        'confidence': round(max(0.0, min(1.0, c)), 4),
        'energy': round(max(0.0, min(1.0, e)), 4),
    }


def apply_formula7_residue(prev: float, impact: float) -> float:
    return round(max(-1.0, min(1.0, prev * _RESIDUE_DECAY + impact)), 4)


def formula_catalog() -> dict:
    return {
        'formula_4': {
            'name': 'State Update Model',
            'equation': 'new = cur + delta − DECAY·(cur − baseline)',
            'decay': _DECAY,
            'baseline': dict(_BASELINE),
            'plain': 'Each event nudges happiness/confidence/energy, then drifts toward baseline.',
        },
        'formula_7': {
            'name': 'Emotional Residue',
            'equation': 'new_residue = prev·RESIDUE_DECAY + impact',
            'residue_decay': _RESIDUE_DECAY,
            'range': [-1.0, 1.0],
            'plain': 'Carryover feeling from recent events; decays ~12% per interaction.',
        },
        'formula_8': {
            'name': 'Emotion Selection',
            'equation': 'score = 0.40·happiness + 0.35·confidence + 0.15·energy + 0.10·residue',
            'weights': dict(_EMO_W),
            'plain': 'Maps the live vector to a mood label agents speak from.',
        },
    }


def _trace_path(layout: StateLayout) -> Path:
    return layout.user_data_root / 'emotion_traces.jsonl'


def build_emotion_trace(
    *,
    entity_id: str,
    markers_hit: list[str] | None = None,
    intent: str = 'self_state',
    source: str = 'expansion',
    user_message: str = '',
    answer_excerpt: str = '',
    layout: Optional[StateLayout] = None,
) -> dict:
    layout = layout or resolve_layout()
    vec = get_emotion_vector(entity_id, layout=layout)
    bond = load_bond(entity_id, layout=layout)
    return {
        'ts': time.time(),
        'entity_id': canonical_entity_id(entity_id),
        'intent': intent,
        'source': source,
        'markers_hit': list(markers_hit or []),
        'vector': {
            'mood': vec.get('mood'),
            'happiness': vec.get('happiness'),
            'confidence': vec.get('confidence'),
            'energy': vec.get('energy'),
            'residue': vec.get('residue'),
            'formula8_score': vec.get('formula8_score'),
        },
        'bond': {
            'trust': bond.get('trust'),
            'affection': bond.get('affection'),
            'placeholder': bool(bond.get('_placeholder')),
        },
        # Never store raw owner message text in traces by default
        'user_message_len': len(user_message or ''),
        'answer_excerpt_len': len(answer_excerpt or ''),
    }


def append_emotion_trace(trace: dict, *, layout: Optional[StateLayout] = None) -> None:
    layout = layout or resolve_layout()
    path = _trace_path(layout)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(trace, ensure_ascii=False) + '\n')


def markers_in_message(message: str) -> list[str]:
    msg = (message or '').lower()
    hits = []
    for m in (
        'how are you', 'how do you feel', 'your mood', 'emotion',
        'stressed', 'happy', 'angry', 'tired',
    ):
        if m in msg:
            hits.append(m)
    return hits
