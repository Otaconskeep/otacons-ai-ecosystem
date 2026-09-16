"""Objective journal engine — WHAT HAPPENED.

Journal entries originate from real events/jobs/interactions.
Reconstructable from underlying events. Never fictional operational history.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.persist import append_jsonl, read_jsonl
from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import MIGRATION_ENGINE_VERSION

JOURNAL_SCHEMA_VERSION = 1


@dataclass
class JournalEntry:
    schema_version: int
    entry_id: str
    timestamp: float
    agent_id: str
    event_ids: tuple
    event_type: str
    actor: str
    target: str
    summary: str
    objective_result: str
    relationship_effects: list = field(default_factory=list)
    emotion_effects: list = field(default_factory=list)
    memory_ids: tuple = ()
    evidence_ids: tuple = ()
    job_id: str = ''
    confidence: float = 1.0

    def validate(self) -> list:
        errors = []
        if self.schema_version != JOURNAL_SCHEMA_VERSION:
            errors.append(f'unsupported journal schema_version {self.schema_version}')
        if not self.entry_id or not self.agent_id:
            errors.append('entry_id and agent_id required')
        if not self.event_ids and not self.job_id:
            errors.append('journal entry must reference event_ids and/or job_id')
        if not self.summary.strip():
            errors.append('summary required')
        if not (0.0 <= self.confidence <= 1.0):
            errors.append('confidence must be in [0,1]')
        # No fictional marker language
        banned = ('imagined that the owner', 'pretended the user', 'fabricated meeting')
        low = self.summary.lower()
        for b in banned:
            if b in low:
                errors.append('journal must not fabricate owner interactions')
        return errors


def new_journal_entry(
    *,
    agent_id: str,
    event_type: str,
    summary: str,
    objective_result: str,
    actor: str = '',
    target: str = '',
    event_ids: tuple = (),
    job_id: str = '',
    relationship_effects: Optional[list] = None,
    emotion_effects: Optional[list] = None,
    memory_ids: tuple = (),
    evidence_ids: tuple = (),
    confidence: float = 1.0,
    timestamp: Optional[float] = None,
) -> JournalEntry:
    return JournalEntry(
        schema_version=JOURNAL_SCHEMA_VERSION,
        entry_id=f'jnl_{uuid.uuid4().hex[:12]}',
        timestamp=time.time() if timestamp is None else timestamp,
        agent_id=agent_id,
        event_ids=tuple(event_ids or ()),
        event_type=event_type,
        actor=actor,
        target=target,
        summary=summary,
        objective_result=objective_result,
        relationship_effects=list(relationship_effects or []),
        emotion_effects=list(emotion_effects or []),
        memory_ids=tuple(memory_ids or ()),
        evidence_ids=tuple(evidence_ids or ()),
        job_id=job_id or '',
        confidence=confidence,
    )


class JournalStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_journals.mkdir(parents=True, exist_ok=True)
        self._index = self.layout.user_journals / 'index.jsonl'

    def _agent_path(self, agent_id: str) -> Path:
        return self.layout.user_journals / f'{agent_id}.jsonl'

    def append(self, entry: JournalEntry) -> JournalEntry:
        errors = entry.validate()
        if errors:
            raise ValueError('; '.join(errors))
        record = asdict(entry)
        append_jsonl(self._agent_path(entry.agent_id), record)
        append_jsonl(self._index, {
            'entry_id': entry.entry_id,
            'agent_id': entry.agent_id,
            'timestamp': entry.timestamp,
            'event_ids': list(entry.event_ids),
            'job_id': entry.job_id,
            'event_type': entry.event_type,
        })
        return entry

    def _load_agent(self, agent_id: str) -> list[JournalEntry]:
        rows = read_jsonl(self._agent_path(agent_id))
        out = []
        for d in rows:
            if isinstance(d.get('event_ids'), list):
                d['event_ids'] = tuple(d['event_ids'])
            if isinstance(d.get('memory_ids'), list):
                d['memory_ids'] = tuple(d['memory_ids'])
            if isinstance(d.get('evidence_ids'), list):
                d['evidence_ids'] = tuple(d['evidence_ids'])
            fields = JournalEntry.__dataclass_fields__
            out.append(JournalEntry(**{k: d[k] for k in fields if k in d}))
        return out

    def recent(self, *, limit: int = 50, agent_id: Optional[str] = None) -> list[JournalEntry]:
        if agent_id:
            rows = self._load_agent(agent_id)
        else:
            rows = []
            for path in sorted(self.layout.user_journals.glob('*.jsonl')):
                if path.name == 'index.jsonl':
                    continue
                rows.extend(self._load_agent(path.stem))
        rows.sort(key=lambda e: e.timestamp, reverse=True)
        return rows[:limit]

    def by_event(self, event_id: str, *, limit: int = 50) -> list[JournalEntry]:
        return [e for e in self.recent(limit=500) if event_id in e.event_ids][:limit]

    def by_job(self, job_id: str, *, limit: int = 50) -> list[JournalEntry]:
        return [e for e in self.recent(limit=500) if e.job_id == job_id][:limit]

    def by_time(
        self,
        *,
        start_ts: float = 0.0,
        end_ts: Optional[float] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[JournalEntry]:
        end_ts = time.time() if end_ts is None else end_ts
        rows = self.recent(limit=1000, agent_id=agent_id)
        return [e for e in rows if start_ts <= e.timestamp <= end_ts][:limit]
