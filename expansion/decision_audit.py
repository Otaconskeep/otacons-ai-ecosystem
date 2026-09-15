"""Decision audit record for Otacon Expansion.

What makes the War Room's decision queue real rather than decorative:
every time an agent answers or takes action, enough gets persisted here to
inspect routing after the fact -- "why did Vector answer instead of
Sentry" should be diagnosable from this record, not from re-asking the LLM.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


def new_decision_id() -> str:
    return f'dec_{uuid.uuid4().hex[:16]}'


@dataclass
class DecisionRecord:
    decision_id: str
    timestamp: float
    session_id: str
    input_text: str
    classified_intent: str
    classified_domain: str
    selected_owner: str
    candidate_agents: tuple
    confidence: float
    relevant_memory_ids: tuple = ()
    relationship_influence: dict = field(default_factory=dict)
    emotional_influence: dict = field(default_factory=dict)
    tools_considered: tuple = ()
    tools_called: tuple = ()
    outcome: str = 'pending'  # 'success' | 'error' | 'pending'
    error: Optional[str] = None
    latency_ms: Optional[float] = None

    def finalize(self, *, outcome: str, latency_ms: float, error: str = None) -> None:
        self.outcome = outcome
        self.latency_ms = latency_ms
        self.error = error


def new_decision(session_id, input_text, classified_intent, classified_domain,
                  selected_owner, candidate_agents, confidence) -> DecisionRecord:
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f'confidence must be in [0,1], got {confidence}')
    return DecisionRecord(
        decision_id=new_decision_id(), timestamp=time.time(), session_id=session_id,
        input_text=input_text, classified_intent=classified_intent,
        classified_domain=classified_domain, selected_owner=selected_owner,
        candidate_agents=tuple(candidate_agents), confidence=confidence,
    )
