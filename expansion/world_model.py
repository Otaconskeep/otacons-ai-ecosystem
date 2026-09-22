"""Operational world model for Expansion Premium (clean-room).

Built from route_learning records/traces + public roster agents.
Contextual layer only — enriches REX discovery; does not override policy.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from expansion.persist import read_json
from expansion.route_learning import list_records
from expansion.state_layout import StateLayout, resolve_layout

_CACHE_TTL_S = 300.0
_LOW_CONFIDENCE_THRESHOLD = 0.55

_world_model_instance: Optional['WorldModel'] = None


def _load_jsonl(path: Path, max_lines: int = 500) -> list[dict]:
    if not path.is_file():
        return []
    try:
        lines = [ln for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip()]
        out = []
        for ln in lines[-max_lines:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
    except OSError:
        return []


def _roster_agents(layout: StateLayout) -> dict[str, dict]:
    agents: dict[str, dict] = {}
    root = layout.user_agents
    if not root.is_dir():
        return agents
    for path in sorted(root.glob('default-*.json')):
        raw = read_json(path, default=None) or {}
        aid = (raw.get('agent_id') or path.stem.replace('default-', '')).strip()
        if not aid:
            continue
        agents[aid] = {
            'name': aid,
            'display': raw.get('display_name') or raw.get('name') or aid,
            'domains': list(raw.get('domains') or raw.get('roles') or []),
            'jobs': [],
        }
    return agents


class WorldModel:
    """Operational awareness: agents, domains, risks, per-entity query stats."""

    def __init__(self, layout: Optional[StateLayout] = None) -> None:
        self.layout = layout or resolve_layout()
        self._built_at = 0.0
        self._agents: dict[str, dict] = {}
        self._domains: dict[str, dict] = {}
        self._risks: list[dict] = []
        self._trace_stats: dict[str, dict] = {}
        self._insights: list[dict] = []

    def build(self) -> None:
        try:
            traces = _load_jsonl(self.layout.user_learning / 'intelligence_traces.jsonl')
            records = list_records(self.layout, limit=800)
            self._agents = _roster_agents(self.layout)
            self._build_domains_from_records(records)
            self._build_trace_stats(traces)
            self._build_risks(traces, records)
            self._built_at = time.monotonic()
        except Exception:
            self._built_at = time.monotonic()

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._built_at) > _CACHE_TTL_S or self._built_at == 0.0

    def _ensure_built(self) -> None:
        if self._is_stale():
            self.build()

    def _build_domains_from_records(self, records: list[dict]) -> None:
        domains: dict[str, dict] = {}
        for rec in records:
            ctx = rec.get('context') or {}
            domain = (ctx.get('domain') or 'ops').strip() or 'ops'
            entry = domains.setdefault(domain, {'domain': domain, 'agents': set(), 'records': 0})
            entry['records'] += 1
            for tag in ctx.get('tags') or []:
                if tag and tag not in ('keeproute', 'omniroute', 'layered-intelligence'):
                    if tag in self._agents:
                        entry['agents'].add(tag)
        for d in domains.values():
            d['agents'] = sorted(d['agents'])
        self._domains = domains

    def _build_trace_stats(self, traces: list[dict]) -> None:
        stats: dict[str, dict] = {}
        for tr in traces:
            eid = tr.get('entity_id') or 'unknown'
            row = stats.setdefault(eid, {
                'categories': {},
                'confidences': [],
                'most_recent_ts': 0.0,
            })
            cat = tr.get('category') or 'unknown'
            row['categories'][cat] = row['categories'].get(cat, 0) + 1
            try:
                row['confidences'].append(float(tr.get('confidence', 0.7)))
            except (TypeError, ValueError):
                pass
            try:
                ts = float(tr.get('ts') or 0)
                if ts > row['most_recent_ts']:
                    row['most_recent_ts'] = ts
            except (TypeError, ValueError):
                pass
        for eid, row in stats.items():
            confs = row.pop('confidences', [])
            row['avg_confidence'] = round(sum(confs) / len(confs), 3) if confs else 0.7
            row['low_confidence_count'] = sum(1 for c in confs if c < _LOW_CONFIDENCE_THRESHOLD)
            row['total_queries'] = sum(row['categories'].values())
        self._trace_stats = stats

    def _build_risks(self, traces: list[dict], records: list[dict]) -> None:
        risks: list[dict] = []
        insights: list[dict] = []
        for eid, st in self._trace_stats.items():
            lc = st.get('low_confidence_count', 0)
            total = st.get('total_queries', 1) or 1
            if lc >= 3 or (lc / total > 0.3 and lc >= 2):
                desc = (
                    f'{eid} has {lc} low-confidence queries '
                    f'({lc}/{total} = {lc / total * 100:.0f}%)'
                )
                item = {
                    'type': 'low_confidence_cluster',
                    'entity': eid,
                    'domain': 'keeproute' if 'keeproute' in eid else '',
                    'description': desc,
                    'severity': 'medium' if lc < 10 else 'high',
                    'score': min(1.0, lc / 20.0),
                }
                risks.append(item)
                insights.append({**item, 'kind': 'insight'})

        for rec in records:
            if rec.get('success', True):
                continue
            ctx = rec.get('context') or {}
            domain = ctx.get('domain') or 'keeproute'
            conf = float(rec.get('confidence') or 0.5)
            risks.append({
                'type': 'operation_failure',
                'entity': '',
                'domain': domain,
                'description': f"Operation failure: {str(rec.get('problem') or '')[:100]}",
                'severity': 'high' if conf < 0.3 else 'medium',
                'score': 1.0 - conf,
                'record_id': rec.get('record_id'),
            })

        risks.sort(key=lambda r: r.get('score', 0), reverse=True)
        self._risks = risks[:20]
        self._insights = insights[:10]

    def get_world_state(self) -> dict[str, Any]:
        self._ensure_built()
        return {
            'agents': list(self._agents.values()),
            'domains': list(self._domains.values()),
            'risks': list(self._risks),
            'insights': list(self._insights),
            'trace_stats': dict(self._trace_stats),
            'built_at': self._built_at,
            'cache_ttl_s': _CACHE_TTL_S,
            'global_pool': True,
        }

    def get_active_risks(self) -> list[dict[str, Any]]:
        self._ensure_built()
        return list(self._risks)

    def proposals_from_risks(self, *, min_score: float = 0.35, limit: int = 3) -> list[dict]:
        """REX proposal sources tagged world_model:*."""
        out = []
        for risk in self.get_active_risks():
            score = float(risk.get('score') or 0)
            if score < min_score:
                continue
            domain = risk.get('domain') or 'coordination'
            if domain == 'keeproute':
                domain = 'infrastructure'
            rtype = risk.get('type') or 'risk'
            out.append({
                'domain': domain,
                'problem': (risk.get('description') or '')[:200],
                'proposal': (
                    f'Investigate and address {rtype} in '
                    f'{risk.get("domain") or risk.get("entity") or "system"}. '
                    f'Severity: {risk.get("severity", "unknown")}.'
                ),
                'confidence': min(0.85, 0.55 + score * 0.30),
                'score': score,
                'source': f'world_model:{rtype}',
                'entity': risk.get('entity') or '',
            })
            if len(out) >= limit:
                break
        return out


def get_world_model(layout: Optional[StateLayout] = None) -> WorldModel:
    global _world_model_instance
    layout = layout or resolve_layout()
    if _world_model_instance is None or _world_model_instance.layout.user_data_root != layout.user_data_root:
        _world_model_instance = WorldModel(layout)
    return _world_model_instance


def invalidate_world_model() -> None:
    global _world_model_instance
    if _world_model_instance is not None:
        _world_model_instance._built_at = 0.0
