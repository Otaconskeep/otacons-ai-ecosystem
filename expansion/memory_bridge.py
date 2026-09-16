"""Expansion memory bridge — layered memory with Core MemoryStore compatibility.

Kinds: working, episodic, semantic, important.

Metadata: timestamp, source, agent, entities, importance, confidence,
event reference, relationship impact, emotion impact.

Does not grow into an unbounded prompt blob — retrieval is ranked + capped.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import MEMORY_SCHEMA_VERSION

MEMORY_KINDS = ('working', 'episodic', 'semantic', 'important')


@dataclass
class MemoryRecord:
    schema_version: int
    memory_id: str
    agent_id: str
    kind: str
    content: str
    timestamp: float
    source: str = ''
    entities: tuple = ()
    importance: float = 0.5
    confidence: float = 0.8
    event_id: str = ''
    relationship_impact: dict = field(default_factory=dict)
    emotion_impact: dict = field(default_factory=dict)
    active: bool = True

    def validate(self) -> list:
        errors = []
        if self.schema_version != MEMORY_SCHEMA_VERSION:
            errors.append(f'unsupported memory schema_version {self.schema_version}')
        if self.kind not in MEMORY_KINDS:
            errors.append(f'unknown memory kind {self.kind!r}')
        if not self.content.strip():
            errors.append('content required')
        if not (0.0 <= self.importance <= 1.0):
            errors.append('importance must be in [0,1]')
        if not (0.0 <= self.confidence <= 1.0):
            errors.append('confidence must be in [0,1]')
        return errors


def new_memory(
    agent_id: str,
    content: str,
    *,
    kind: str = 'episodic',
    source: str = '',
    entities: tuple = (),
    importance: float = 0.5,
    confidence: float = 0.8,
    event_id: str = '',
    relationship_impact: Optional[dict] = None,
    emotion_impact: Optional[dict] = None,
) -> MemoryRecord:
    return MemoryRecord(
        schema_version=MEMORY_SCHEMA_VERSION,
        memory_id=f'mem_{uuid.uuid4().hex[:12]}',
        agent_id=agent_id,
        kind=kind,
        content=content,
        timestamp=time.time(),
        source=source,
        entities=tuple(entities or ()),
        importance=importance,
        confidence=confidence,
        event_id=event_id,
        relationship_impact=dict(relationship_impact or {}),
        emotion_impact=dict(emotion_impact or {}),
        active=True,
    )


class ExpansionMemory:
    """JSONL-per-agent store under user_memory. Bridges optional Core MemoryStore."""

    def __init__(self, layout: Optional[StateLayout] = None, core_store=None):
        self.layout = layout or resolve_layout()
        self.layout.user_memory.mkdir(parents=True, exist_ok=True)
        self.core = core_store  # optional core.memory.MemoryStore

    def _path(self, agent_id: str) -> Path:
        return self.layout.user_memory / f'{agent_id}.jsonl'

    def add(self, record: MemoryRecord) -> MemoryRecord:
        errors = record.validate()
        if errors:
            raise ValueError('; '.join(errors))
        path = self._path(record.agent_id)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(record), default=str) + '\n')
        # Bridge important/semantic facts into Core store when available
        if self.core is not None and record.kind in ('important', 'semantic', 'episodic'):
            try:
                self.core.remember('local_user', record.agent_id, record.content, source=record.event_id or None)
            except Exception:
                pass
        return record

    def list(self, agent_id: str, *, include_inactive: bool = False) -> list[MemoryRecord]:
        path = self._path(agent_id)
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if isinstance(d.get('entities'), list):
                d['entities'] = tuple(d['entities'])
            rec = MemoryRecord(**{k: d[k] for k in MemoryRecord.__dataclass_fields__ if k in d})
            if rec.active or include_inactive:
                out.append(rec)
        return out

    def retrieve(
        self,
        agent_id: str,
        query: str,
        *,
        limit: int = 5,
        kinds: Optional[tuple] = None,
    ) -> list[MemoryRecord]:
        terms = set(query.lower().split())
        rows = self.list(agent_id)
        if kinds:
            rows = [r for r in rows if r.kind in kinds]
        def score(r: MemoryRecord) -> float:
            overlap = sum(t in r.content.lower() for t in terms) if terms else 0
            kind_boost = {'important': 0.3, 'semantic': 0.2, 'episodic': 0.1, 'working': 0.0}.get(r.kind, 0)
            return overlap + r.importance + kind_boost + 0.1 * r.confidence
        ranked = sorted(rows, key=score, reverse=True)
        if terms:
            ranked = [r for r in ranked if any(t in r.content.lower() for t in terms) or r.kind == 'important']
        return ranked[:limit]

    def bridge_from_core(self, agent_id: str, user_id: str = 'local_user') -> int:
        """Import Core facts into Expansion episodic store (idempotent-ish by content)."""
        if self.core is None:
            return 0
        existing = {r.content for r in self.list(agent_id)}
        n = 0
        for row in self.core.list_memories(user_id, agent_id):
            content = row.get('content') or ''
            if not content or content in existing:
                continue
            self.add(new_memory(agent_id, content, kind='semantic', source='core_bridge', importance=0.55))
            n += 1
        return n
