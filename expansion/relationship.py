"""Bounded relationship + mood scoring for Otacon Expansion.

Pure functions only -- no I/O, no LLM calls, no rendering. This is the
canonical-state layer: scores computed here are truth. Any human-language
rendering elsewhere (dossier prose, journal entries, War Room explanations)
is a *rendering* of this, never a second source of truth for it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class EvidenceType(str, Enum):
    DIRECT_INTERACTION = 'direct_interaction'
    OBSERVED_INTERACTION = 'observed_interaction'
    SECONDHAND_REPORT = 'secondhand_report'
    TASK_COLLABORATION = 'task_collaboration'
    INFERRED_BASELINE = 'inferred_baseline'


# event -> (trust_delta, irritation_delta), applied before clamping.
_EVENT_WEIGHTS = {
    'compliment':   (0.06, -0.03),
    'insult':       (-0.10, 0.18),
    'help_given':   (0.08, -0.02),
    'help_received': (0.05, -0.01),
    'task_success': (0.07, -0.02),
    'task_failure': (-0.04, 0.05),
    'apology':      (0.05, -0.08),
    'ignored':      (-0.02, 0.04),
}

TRUST_MIN, TRUST_MAX = 0.0, 1.0
IRRITATION_MIN, IRRITATION_MAX = 0.0, 1.0
NEUTRAL_TRUST = 0.5
NEUTRAL_IRRITATION = 0.0

# Irritation fades fast; trust erodes/builds slowly. A relationship doesn't
# forget years of trust because a day passed, but a flash of irritation
# should fade on its own well before that.
IRRITATION_DECAY_HALF_LIFE_S = 6 * 3600
TRUST_DECAY_HALF_LIFE_S = 30 * 24 * 3600


@dataclass
class RelationshipState:
    trust: float = NEUTRAL_TRUST
    irritation: float = NEUTRAL_IRRITATION
    evidence: EvidenceType = EvidenceType.INFERRED_BASELINE
    event_count: int = 0
    last_event_at: float = 0.0

    def clamp(self) -> 'RelationshipState':
        self.trust = min(TRUST_MAX, max(TRUST_MIN, self.trust))
        self.irritation = min(IRRITATION_MAX, max(IRRITATION_MIN, self.irritation))
        return self


def new_relationship(evidence: EvidenceType = EvidenceType.INFERRED_BASELINE) -> RelationshipState:
    """A freshly created agent's relationship to an existing one: 'no direct
    history yet, secondhand impression only' -- an explicit inferred
    baseline, never presented as a historical fact.
    """
    return RelationshipState(trust=NEUTRAL_TRUST, irritation=NEUTRAL_IRRITATION,
                              evidence=evidence, event_count=0, last_event_at=0.0)


def _decay(value: float, neutral: float, elapsed_s: float, half_life_s: float) -> float:
    if elapsed_s <= 0 or half_life_s <= 0:
        return value
    factor = 0.5 ** (elapsed_s / half_life_s)
    return neutral + (value - neutral) * factor


def apply_decay(state: RelationshipState, now: float = None) -> RelationshipState:
    now = time.time() if now is None else now
    if state.last_event_at <= 0:
        return state
    elapsed = max(0.0, now - state.last_event_at)
    state.trust = _decay(state.trust, NEUTRAL_TRUST, elapsed, TRUST_DECAY_HALF_LIFE_S)
    state.irritation = _decay(state.irritation, NEUTRAL_IRRITATION, elapsed, IRRITATION_DECAY_HALF_LIFE_S)
    return state.clamp()


def apply_event(state: RelationshipState, event: str, *, now: float = None,
                 evidence: EvidenceType = None, weight: float = 1.0) -> RelationshipState:
    """Apply one relationship event: decay existing state to `now`, apply the
    event's weighted delta, then clamp. However large `weight` is, the
    result is always clamped to [0,1] -- no single event can push a
    relationship out of range or make it permanently unrecoverable.
    """
    now = time.time() if now is None else now
    apply_decay(state, now)
    trust_d, irr_d = _EVENT_WEIGHTS.get(event, (0.0, 0.0))
    state.trust += trust_d * weight
    state.irritation += irr_d * weight
    state.clamp()
    state.event_count += 1
    state.last_event_at = now
    if evidence is not None:
        state.evidence = evidence
    elif state.evidence == EvidenceType.INFERRED_BASELINE:
        state.evidence = EvidenceType.DIRECT_INTERACTION
    return state


def classify_affect(state: RelationshipState) -> str:
    """Deterministic trust/irritation -> affect classification. The same
    function renders UI state AND answers 'why does the system believe
    this' -- there is no second, separate explanation path.
    """
    if state.irritation >= 0.75:
        return 'rage'
    if state.irritation >= 0.45:
        return 'angry'
    if state.irritation >= 0.20 and state.trust >= 0.55:
        # irritated, but trust is intact -- a composed persona masks it
        return 'sad_masked'
    if state.trust <= 0.25:
        return 'sad'
    if state.trust >= 0.75 and state.irritation < 0.15:
        return 'happy'
    return 'neutral'


def explain(state: RelationshipState) -> dict:
    """Machine-readable rationale behind classify_affect() -- the payload
    for the War Room's clickable 'why does the system believe this agent
    feels this way' feature. Computed directly from the same state that
    produced the classification; never regenerated after the fact.
    """
    return {
        'trust': round(state.trust, 4),
        'irritation': round(state.irritation, 4),
        'evidence': state.evidence.value,
        'event_count': state.event_count,
        'last_event_at': state.last_event_at,
        'classified_affect': classify_affect(state),
    }
