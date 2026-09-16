"""Emotional state engine for Keep Expansion.

Dimensions (locked): joy, sadness, anger, fear, stress, confidence,
curiosity, frustration, satisfaction, attachment, jealousy, insecurity,
concern, pride, loneliness.

Flow:
  event → weights → personality modifiers → relationship modifiers
       → emotional state → decay/recovery → behavior context

Every significant change carries provenance so the system can answer WHY.
Vulnerabilities color sensitivity; they must not make agents operationally unreliable.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.versions import EMOTION_SCHEMA_VERSION

EMOTION_DIMENSIONS = (
    'joy', 'sadness', 'anger', 'fear', 'stress', 'confidence', 'curiosity',
    'frustration', 'satisfaction', 'attachment', 'jealousy', 'insecurity',
    'concern', 'pride', 'loneliness',
)

# Half-lives (seconds). Stress/anger fade faster than attachment/jealousy.
_DECAY_HALF_LIFE = {
    'joy': 8 * 3600,
    'sadness': 18 * 3600,
    'anger': 4 * 3600,
    'fear': 10 * 3600,
    'stress': 3 * 3600,
    'confidence': 36 * 3600,
    'curiosity': 12 * 3600,
    'frustration': 5 * 3600,
    'satisfaction': 10 * 3600,
    'attachment': 14 * 24 * 3600,
    'jealousy': 20 * 3600,
    'insecurity': 24 * 3600,
    'concern': 8 * 3600,
    'pride': 16 * 3600,
    'loneliness': 20 * 3600,
}

# Neutral resting points (baselines override per agent).
_NEUTRAL = {k: 0.25 for k in EMOTION_DIMENSIONS}
_NEUTRAL.update({
    'confidence': 0.55,
    'curiosity': 0.45,
    'attachment': 0.4,
    'satisfaction': 0.4,
    'stress': 0.15,
    'anger': 0.1,
    'fear': 0.15,
    'jealousy': 0.15,
    'insecurity': 0.2,
    'loneliness': 0.2,
    'concern': 0.2,
    'pride': 0.35,
    'frustration': 0.15,
    'sadness': 0.15,
    'joy': 0.35,
})


@dataclass
class ProvenanceEntry:
    event_id: str
    event_type: str
    deltas: dict
    at: float
    note: str = ''


@dataclass
class EmotionalState:
    schema_version: int
    agent_id: str
    dimensions: dict
    baseline: dict = field(default_factory=dict)
    sensitivity: dict = field(default_factory=dict)  # per-dimension multipliers
    provenance: list = field(default_factory=list)  # recent ProvenanceEntry dicts
    updated_at: float = 0.0
    last_event_at: float = 0.0

    def clamp(self) -> 'EmotionalState':
        for k in EMOTION_DIMENSIONS:
            if k in self.dimensions:
                self.dimensions[k] = min(1.0, max(0.0, float(self.dimensions[k])))
        return self

    def explain(self, dimension: str, limit: int = 5) -> dict:
        """WHY is this dimension at its current value?"""
        hits = []
        for p in reversed(self.provenance):
            d = p.get('deltas') if isinstance(p, dict) else getattr(p, 'deltas', {})
            if dimension in (d or {}):
                hits.append(p if isinstance(p, dict) else asdict(p))
            if len(hits) >= limit:
                break
        return {
            'agent_id': self.agent_id,
            'dimension': dimension,
            'value': round(float(self.dimensions.get(dimension, 0.0)), 4),
            'baseline': round(float(self.baseline.get(dimension, _NEUTRAL.get(dimension, 0.25))), 4),
            'sensitivity': round(float(self.sensitivity.get(dimension, 1.0)), 4),
            'sources': hits,
        }


def default_dimensions(baseline: Optional[dict] = None) -> dict:
    dims = dict(_NEUTRAL)
    if baseline:
        dims.update({k: float(v) for k, v in baseline.items() if k in EMOTION_DIMENSIONS})
    for k in EMOTION_DIMENSIONS:
        dims[k] = min(1.0, max(0.0, float(dims[k])))
    return dims


def new_emotional_state(
    agent_id: str,
    *,
    baseline: Optional[dict] = None,
    sensitivity: Optional[dict] = None,
) -> EmotionalState:
    base = default_dimensions(baseline)
    sens = {k: 1.0 for k in EMOTION_DIMENSIONS}
    if sensitivity:
        sens.update({k: float(v) for k, v in sensitivity.items() if k in EMOTION_DIMENSIONS})
    now = time.time()
    return EmotionalState(
        schema_version=EMOTION_SCHEMA_VERSION,
        agent_id=agent_id,
        dimensions=dict(base),
        baseline=dict(base),
        sensitivity=sens,
        provenance=[],
        updated_at=now,
        last_event_at=0.0,
    ).clamp()


def _decay(value: float, neutral: float, elapsed_s: float, half_life_s: float) -> float:
    if elapsed_s <= 0 or half_life_s <= 0:
        return value
    factor = 0.5 ** (elapsed_s / half_life_s)
    return neutral + (value - neutral) * factor


def apply_decay(state: EmotionalState, now: Optional[float] = None) -> EmotionalState:
    now = time.time() if now is None else now
    if state.last_event_at <= 0 and state.updated_at <= 0:
        return state
    anchor = state.last_event_at or state.updated_at
    elapsed = max(0.0, now - anchor)
    for k in EMOTION_DIMENSIONS:
        neutral = float(state.baseline.get(k, _NEUTRAL.get(k, 0.25)))
        state.dimensions[k] = _decay(
            float(state.dimensions.get(k, neutral)),
            neutral,
            elapsed,
            _DECAY_HALF_LIFE.get(k, 12 * 3600),
        )
    state.updated_at = now
    return state.clamp()


def apply_emotion_deltas(
    state: EmotionalState,
    raw_deltas: dict,
    *,
    event_id: str,
    event_type: str,
    personality_modifiers: Optional[dict] = None,
    relationship_modifiers: Optional[dict] = None,
    note: str = '',
    now: Optional[float] = None,
) -> EmotionalState:
    """Apply weighted emotion deltas with modifiers + provenance."""
    if not event_id:
        raise ValueError('event_id required for emotion provenance')
    now = time.time() if now is None else now
    apply_decay(state, now)

    personality_modifiers = personality_modifiers or {}
    relationship_modifiers = relationship_modifiers or {}
    applied = {}
    for dim, delta in raw_deltas.items():
        if dim not in EMOTION_DIMENSIONS:
            continue
        sens = float(state.sensitivity.get(dim, 1.0))
        pmod = float(personality_modifiers.get(dim, 1.0))
        rmod = float(relationship_modifiers.get(dim, 1.0))
        final = float(delta) * sens * pmod * rmod
        state.dimensions[dim] = float(state.dimensions.get(dim, 0.0)) + final
        applied[dim] = round(final, 6)

    state.clamp()
    state.last_event_at = now
    state.updated_at = now
    entry = asdict(ProvenanceEntry(
        event_id=event_id,
        event_type=event_type,
        deltas=applied,
        at=now,
        note=note,
    ))
    state.provenance = list(state.provenance[-49:]) + [entry]
    return state


def to_dict(state: EmotionalState) -> dict:
    return asdict(state)


def from_dict(d: dict) -> EmotionalState:
    d = dict(d)
    fields = EmotionalState.__dataclass_fields__
    return EmotionalState(**{k: v for k, v in d.items() if k in fields}).clamp()
