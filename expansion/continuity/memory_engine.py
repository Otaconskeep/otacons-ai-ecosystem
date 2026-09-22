# -*- coding: utf-8 -*-
"""Memory Engine — Formula 9 retrieval scoring for public Expansion Premium.

topic match + emotional weight + recency + repetition penalty.
Clean-room Keep-parity. Stores reflections under owner-local continuity_memory/.
Never reads private Keep memory paths.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout

PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})
_REFLECTION_INTERVAL = 20
_lock = threading.Lock()


def _canon(raw: str | None) -> str:
    s = (raw or '').strip().lower().replace('-', '_').replace(' ', '_')
    if s in ('owner', 'user', 'operator'):
        return 'user_primary'
    return s


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _entity_dir(layout: StateLayout, entity_id: str) -> Path:
    safe = _canon(entity_id).replace('/', '_')[:80] or 'unknown'
    d = Path(layout.user_data_root) / 'continuity_memory' / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def score_memory_entry(
    entry: dict,
    query_terms: list[str],
    current_entity: str,
    recency_rank: int,
    prior_served_ids: set,
) -> float:
    """Formula 9 — Memory Retrieval Score in [0, 1]."""
    score = 0.0
    text = (entry.get('text') or entry.get('note') or entry.get('summary')
            or entry.get('content') or '').lower()

    match_count = sum(1 for t in query_terms if t and t.lower() in text)
    score += min(match_count * 0.25, 0.50)
    if current_entity and current_entity.lower().replace('_', ' ') in text:
        score += 0.15

    sentiment = (
        entry.get('sentiment')
        or (entry.get('payload') or {}).get('sentiment')
        or 'neutral'
    )
    if isinstance(sentiment, str):
        score += {'negative': 0.15, 'positive': 0.10}.get(sentiment.lower(), 0.0)

    score += max(0.0, 0.20 - recency_rank * 0.02)

    entry_id = str(entry.get('id') or entry.get('ts') or entry.get('memory_id') or '')
    if entry_id and entry_id in prior_served_ids:
        score -= 0.30

    return round(max(0.0, min(1.0, score)), 4)


def score_and_rank(
    entries: list[dict],
    query_terms: list[str],
    current_entity: str,
    prior_served_ids: set | None = None,
    top_k: int = 6,
) -> list[dict]:
    prior_served_ids = prior_served_ids or set()
    scored = []
    for rank, entry in enumerate(entries):
        s = score_memory_entry(entry, query_terms, current_entity, rank, prior_served_ids)
        scored.append((s, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for s, e in scored[:top_k]:
        row = dict(e)
        row['_formula9_score'] = s
        out.append(row)
    return out


def query_terms_from_message(message: str, *, limit: int = 12) -> list[str]:
    stop = {
        'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'is', 'are',
        'me', 'my', 'you', 'your', 'we', 'it', 'this', 'that', 'with', 'from',
        'please', 'just', 'can', 'could', 'would', 'should', 'what', 'how', 'why',
    }
    tokens = re.findall(r"[a-z0-9']{3,}", (message or '').lower())
    out = []
    for t in tokens:
        if t in stop:
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


class MemoryEngine:
    """Formula 9 memory + reflection engine for Premium Expansion."""

    @staticmethod
    def load_continuity(entity_id: str, *, layout: Optional[StateLayout] = None) -> dict:
        layout = layout or resolve_layout()
        path = _entity_dir(layout, entity_id) / 'continuity.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {
            'last_active': '',
            'interaction_count': 0,
            'last_reflection_ts': '',
            'total_reflections': 0,
        }

    @staticmethod
    def save_continuity(entity_id: str, state: dict, *, layout: Optional[StateLayout] = None) -> bool:
        layout = layout or resolve_layout()
        path = _entity_dir(layout, entity_id) / 'continuity.json'
        try:
            path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            return True
        except Exception:
            return False

    @staticmethod
    def record_interaction(entity_id: str, *, layout: Optional[StateLayout] = None) -> dict:
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        if eid not in PUBLIC_AGENTS:
            return MemoryEngine.load_continuity(eid, layout=layout)
        with _lock:
            state = MemoryEngine.load_continuity(eid, layout=layout)
            state['last_active'] = _now_iso()
            state['interaction_count'] = int(state.get('interaction_count', 0)) + 1
            MemoryEngine.save_continuity(eid, state, layout=layout)
        count = int(state['interaction_count'])
        if count % _REFLECTION_INTERVAL == 0:
            MemoryEngine.write_reflection(
                eid,
                trigger='interaction_count',
                note=f'Reached {count} interactions. Ongoing operational presence.',
                layout=layout,
            )
        return state

    @staticmethod
    def write_reflection(
        entity_id: str,
        trigger: str,
        note: str,
        payload: dict | None = None,
        emotional_weight: str = 'neutral',
        *,
        layout: Optional[StateLayout] = None,
    ) -> dict:
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        # Scrub accidental private path markers from notes
        scrubbed = note or ''
        for leak in ('/opt/otacon', '192.168.50.', '/mnt/data/', 'xof'):
            if leak in scrubbed.lower():
                scrubbed = '[redacted reflection]'
                break
        entry = {
            'id': f'ref_{int(time.time() * 1000)}',
            'ts': _now_iso(),
            'trigger': trigger,
            'note': scrubbed[:500],
            'payload': payload or {},
            'sentiment': emotional_weight if emotional_weight in (
                'positive', 'negative', 'neutral',
            ) else 'neutral',
        }
        path = _entity_dir(layout, eid) / 'reflections.jsonl'
        with _lock:
            try:
                with path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except Exception:
                pass
            state = MemoryEngine.load_continuity(eid, layout=layout)
            state['last_reflection_ts'] = entry['ts']
            state['total_reflections'] = int(state.get('total_reflections', 0)) + 1
            MemoryEngine.save_continuity(eid, state, layout=layout)
        return entry

    @staticmethod
    def recent_reflections(
        entity_id: str, limit: int = 5, *, layout: Optional[StateLayout] = None,
    ) -> list[dict]:
        layout = layout or resolve_layout()
        path = _entity_dir(layout, entity_id) / 'reflections.jsonl'
        if not path.is_file():
            return []
        results: list[dict] = []
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
                if len(results) >= limit:
                    break
        except Exception:
            pass
        return results

    @staticmethod
    def scored_reflections(
        entity_id: str,
        query_terms: list[str],
        top_k: int = 3,
        *,
        layout: Optional[StateLayout] = None,
    ) -> list[dict]:
        layout = layout or resolve_layout()
        all_refs = MemoryEngine.recent_reflections(entity_id, limit=40, layout=layout)
        return score_and_rank(all_refs, query_terms, _canon(entity_id), top_k=top_k)

    @staticmethod
    def load_duties(entity_id: str, *, layout: Optional[StateLayout] = None) -> dict:
        layout = layout or resolve_layout()
        path = _entity_dir(layout, entity_id) / 'duties.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {'duties': [], 'routines': [], 'mandates': [], 'updated': ''}

    @staticmethod
    def duties_prompt_line(entity_id: str, *, layout: Optional[StateLayout] = None) -> str:
        d = MemoryEngine.load_duties(entity_id, layout=layout)
        parts = []
        if d.get('duties'):
            parts.append('Duties: ' + '; '.join(list(d['duties'])[:4]))
        if d.get('routines'):
            parts.append('Routines: ' + '; '.join(list(d['routines'])[:3]))
        if d.get('mandates'):
            parts.append('Mandates: ' + '; '.join(list(d['mandates'])[:3]))
        return ' | '.join(parts) if parts else ''

    @staticmethod
    def retrieve_relevant_memory(
        entity_id: str,
        query: str,
        *,
        top_k: int = 6,
        prior_served_ids: set | None = None,
        layout: Optional[StateLayout] = None,
    ) -> list[dict]:
        """Unify ExpansionMemory + reflections; score with Formula 9."""
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        terms = query_terms_from_message(query)
        entries: list[dict] = []

        # Reflections first (slight retrieval advantage — no rank offset)
        for ref in MemoryEngine.recent_reflections(eid, limit=40, layout=layout):
            row = dict(ref)
            row.setdefault('note', ref.get('note') or '')
            row['_source'] = 'reflection'
            entries.append(row)

        # Expansion episodic / product memory
        try:
            from expansion.memory_bridge import ExpansionMemory
            mem = ExpansionMemory(layout)
            for m in mem.retrieve(eid, query or eid, limit=40):
                entries.append({
                    'id': getattr(m, 'memory_id', '') or '',
                    'text': getattr(m, 'content', '') or '',
                    'note': getattr(m, 'content', '') or '',
                    'kind': getattr(m, 'kind', '') or '',
                    'sentiment': 'neutral',
                    'importance': getattr(m, 'importance', 0.5),
                    '_source': 'episodic',
                })
        except Exception:
            pass

        # Learned claims as soft memory
        try:
            from expansion.learning import LearningEngine
            for line in LearningEngine(layout).context_lines(eid, limit=12):
                entries.append({
                    'id': f'learn_{hash(line) & 0xffffffff:08x}',
                    'note': line.lstrip('- ').strip(),
                    'sentiment': 'neutral',
                    '_source': 'learning',
                })
        except Exception:
            pass

        return score_and_rank(
            entries, terms, eid,
            prior_served_ids=prior_served_ids or set(),
            top_k=top_k,
        )

    @staticmethod
    def memory_prompt_block(
        entity_id: str,
        query: str,
        *,
        top_k: int = 5,
        layout: Optional[StateLayout] = None,
    ) -> str:
        rows = MemoryEngine.retrieve_relevant_memory(
            entity_id, query, top_k=top_k, layout=layout,
        )
        if not rows:
            return ''
        lines = []
        for r in rows:
            score = r.get('_formula9_score', 0)
            src = r.get('_source') or 'memory'
            text = (r.get('note') or r.get('text') or r.get('content') or '').strip()
            if not text:
                continue
            lines.append(f'- ({src} f9={score:.2f}) {text[:180]}')
        if not lines:
            return ''
        return '[Agent memory — Formula 9 scored]\n' + '\n'.join(lines)
