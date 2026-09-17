"""Subjective diary engine — WHAT THE EVENT MEANT TO THE AGENT.

Diary does not alter objective facts. Always references journal/event sources.
Never fabricates owner interactions that did not happen.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.canonical_dossiers import get_canonical_dossier
from expansion.emotion_store import EmotionStore
from expansion.journal import JournalEntry, JournalStore
from expansion.persist import append_jsonl, read_jsonl
from expansion.relationship_store import RelationshipStore
from expansion.state_layout import StateLayout, resolve_layout

DIARY_SCHEMA_VERSION = 1


@dataclass
class DiaryEntry:
    schema_version: int
    diary_id: str
    agent_id: str
    timestamp: float
    source_journal_ids: tuple
    source_event_ids: tuple
    emotional_state_snapshot: dict
    relationship_refs: list
    text: str
    generation: dict = field(default_factory=dict)  # model/provider metadata
    why: dict = field(default_factory=dict)  # explainability payload

    def validate(self) -> list:
        errors = []
        if self.schema_version != DIARY_SCHEMA_VERSION:
            errors.append(f'unsupported diary schema_version {self.schema_version}')
        if not self.diary_id or not self.agent_id:
            errors.append('diary_id and agent_id required')
        if not self.source_journal_ids and not self.source_event_ids:
            errors.append('diary must cite source_journal_ids or source_event_ids')
        if not self.text.strip():
            errors.append('text required')
        banned = (
            'the owner told me yesterday',
            'we met in person',
            'i remember when you and i',
        )
        low = self.text.lower()
        for b in banned:
            if b in low:
                errors.append('diary must not fabricate owner history')
        return errors


def _template_diary(agent_id: str, journal: JournalEntry, emotion: dict, dossier) -> tuple[str, dict]:
    """Deterministic local diary text (no LLM required for P2 correctness)."""
    arch = dossier.character.archetype
    style = (getattr(dossier.character, 'diary_style', None) or '').strip()
    top = sorted(emotion.items(), key=lambda kv: kv[1], reverse=True)[:4]
    feeling = ', '.join(f'{k}={v:.2f}' for k, v in top)
    vulns = [
        v.label for v in dossier.vulnerabilities.items
        if not getattr(v, 'intentional_absence', False)
    ][:3]
    if style:
        text = (
            f"[{style}] {journal.summary} — objective: {journal.objective_result}. "
            f"Afterward I sat with {feeling}. "
            f"Pressures in play: {', '.join(vulns) or 'none noted'}."
        )
    else:
        text = (
            f"({arch}) Reflecting on: {journal.summary}. "
            f"Objective result was {journal.objective_result}. "
            f"My state afterward: {feeling}. "
            f"This touches my known pressures: {', '.join(vulns) or 'none noted'}."
        )
    why = {
        'source_summary': journal.summary,
        'objective_result': journal.objective_result,
        'archetype': arch,
        'diary_style': style or None,
        'emotion_highlights': dict(top),
        'vulnerability_labels': vulns,
        'generator': 'template_v2' if style else 'template_v1',
        'rule': 'Diary interprets journal facts; it does not invent events.',
    }
    return text, why


class DiaryStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_diaries.mkdir(parents=True, exist_ok=True)
        self.journals = JournalStore(self.layout)
        self.emotions = EmotionStore(self.layout)
        self.relationships = RelationshipStore(self.layout)

    def _path(self, agent_id: str) -> Path:
        return self.layout.user_diaries / f'{agent_id}.jsonl'

    def generate_from_journal(
        self,
        journal: JournalEntry,
        *,
        generation: Optional[dict] = None,
    ) -> DiaryEntry:
        dossier = get_canonical_dossier(journal.agent_id)
        emo = self.emotions.get_or_create(journal.agent_id)
        text, why = _template_diary(
            journal.agent_id, journal, dict(emo.dimensions), dossier,
        )
        rels = self.relationships.all_for(journal.agent_id)
        refs = [
            {'source': r.source_id, 'target': r.target_id}
            for r in rels if r.source_id == journal.agent_id
        ][:8]
        entry = DiaryEntry(
            schema_version=DIARY_SCHEMA_VERSION,
            diary_id=f'diary_{uuid.uuid4().hex[:12]}',
            agent_id=journal.agent_id,
            timestamp=time.time(),
            source_journal_ids=(journal.entry_id,),
            source_event_ids=tuple(journal.event_ids),
            emotional_state_snapshot={k: round(v, 4) for k, v in emo.dimensions.items()},
            relationship_refs=refs,
            text=text,
            generation=generation or {'provider': 'local_template', 'model': 'template_v1'},
            why=why,
        )
        errors = entry.validate()
        if errors:
            raise ValueError('; '.join(errors))
        append_jsonl(self._path(journal.agent_id), asdict(entry))
        return entry

    def recent(self, agent_id: str, *, limit: int = 50) -> list[dict]:
        rows = read_jsonl(self._path(agent_id))
        rows.sort(key=lambda d: d.get('timestamp', 0), reverse=True)
        return rows[:limit]

    def explain(self, agent_id: str, diary_id: str) -> dict:
        for row in self.recent(agent_id, limit=500):
            if row.get('diary_id') == diary_id:
                return {
                    'diary_id': diary_id,
                    'text': row.get('text'),
                    'why': row.get('why') or {},
                    'source_journal_ids': row.get('source_journal_ids') or [],
                    'source_event_ids': row.get('source_event_ids') or [],
                    'emotional_state_snapshot': row.get('emotional_state_snapshot') or {},
                    'generation': row.get('generation') or {},
                }
        raise KeyError(diary_id)
