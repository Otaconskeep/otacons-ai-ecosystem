"""Common Expansion event model (skeleton).

Subsystems (memory, emotion, relationships, journal, living dossier, UI,
notifications) consume events instead of calling each other directly.
P0 defines the schema and an in-memory / JSONL bus; durable routing comes later.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import EVENT_SCHEMA_VERSION

# Initial event type catalog (locked for P0/P1 foundation).
EVENT_TYPES = (
    'job.created',
    'job.assigned',
    'job.completed',
    'job.failed',
    'job.delegated',
    'agent.selected',
    'agent.message',
    'relationship.changed',
    'emotion.changed',
    'service.failed',
    'service.recovered',
    'user.praised_agent',
    'user.corrected_agent',
    'user.apologized_to_agent',
    'user.insulted_agent',
    'user.compared_agents',
    'memory.created',
    'journal.created',
    'diary.created',
    # Foundation / provision
    'provision.started',
    'provision.step',
    'provision.completed',
    'provision.failed',
    'provision.rolled_back',
)


@dataclass
class Event:
    schema_version: int
    event_id: str
    event_type: str
    timestamp: float
    actor: str = ''           # agent_id, 'user', 'system', service name
    subject: str = ''         # primary entity affected
    payload: dict = field(default_factory=dict)
    provenance: list = field(default_factory=list)  # prior event_ids / refs
    correlation_id: str = ''

    def validate(self) -> list:
        errors = []
        if self.schema_version != EVENT_SCHEMA_VERSION:
            errors.append(f'unsupported event schema_version {self.schema_version}')
        if self.event_type not in EVENT_TYPES:
            errors.append(f'unknown event_type {self.event_type!r}')
        if not self.event_id:
            errors.append('event_id required')
        return errors


def new_event(
    event_type: str,
    *,
    actor: str = '',
    subject: str = '',
    payload: Optional[dict] = None,
    provenance: Optional[list] = None,
    correlation_id: str = '',
    timestamp: Optional[float] = None,
) -> Event:
    return Event(
        schema_version=EVENT_SCHEMA_VERSION,
        event_id=f'evt_{uuid.uuid4().hex}',
        event_type=event_type,
        timestamp=time.time() if timestamp is None else timestamp,
        actor=actor,
        subject=subject,
        payload=dict(payload or {}),
        provenance=list(provenance or []),
        correlation_id=correlation_id or '',
    )


Subscriber = Callable[[Event], None]


class EventBus:
    """Process-local bus with optional JSONL append for user-state durability."""

    def __init__(self, layout: Optional[StateLayout] = None, persist: bool = True):
        self.layout = layout or resolve_layout()
        self.persist = persist
        self._subs: list[tuple[Optional[str], Subscriber]] = []
        self._buffer: list[Event] = []

    def subscribe(self, fn: Subscriber, event_type: Optional[str] = None) -> None:
        self._subs.append((event_type, fn))

    def _log_path(self) -> Path:
        return self.layout.user_events / 'events.jsonl'

    def emit(self, event: Event) -> Event:
        errors = event.validate()
        if errors:
            raise ValueError('; '.join(errors))
        self._buffer.append(event)
        if self.persist:
            self.layout.user_events.mkdir(parents=True, exist_ok=True)
            with self._log_path().open('a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(event), default=str) + '\n')
        for etype, fn in self._subs:
            if etype is None or etype == event.event_type:
                fn(event)
        return event

    def recent(self, limit: int = 100) -> list[Event]:
        if self._buffer:
            return list(self._buffer[-limit:])
        path = self._log_path()
        if not path.exists():
            return []
        lines = path.read_text(encoding='utf-8').splitlines()[-limit:]
        out = []
        for line in lines:
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(Event(**{k: d[k] for k in Event.__dataclass_fields__ if k in d}))
        return out
