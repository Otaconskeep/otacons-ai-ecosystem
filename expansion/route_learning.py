"""KeepRoute / OmniRoute → Expansion global learning pool (clean-room).

Every routed exchange can record into a shared install-wide store under
user_learning/. domain: keeproute is a tag, not a silo. World model + REX
consume the same pool.

Fail-open: never raises to callers.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from typing import Any, Optional

from expansion.persist import append_jsonl, read_json, update_json
from expansion.state_layout import StateLayout, resolve_layout

_DEDUPE_TTL_S = 90.0
_dedupe_lock = threading.Lock()
_recent: dict[str, float] = {}

_AGENT_ALIASES = {
    'auto': 'keeproute-auto',
    'llm': 'ollama-local',
    'local': 'ollama-local',
    'ollama': 'ollama-local',
    'ollama-local': 'ollama-local',
    'claude': 'claude',
    'cc': 'claude',
    'codex': 'codex',
    'cx': 'codex',
    'cursor': 'cursor',
    'cursor-agent': 'cursor',
    'cu': 'cursor',
    'grok': 'grok',
    'grok-cli': 'grok',
    'gc': 'grok',
}


def _clip(text: str, n: int) -> str:
    t = (text or '').strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + '…'


def _norm_agent(agent: str | None, model: str | None = None) -> str:
    a = (agent or '').strip().lower()
    if a in _AGENT_ALIASES:
        return _AGENT_ALIASES[a]
    m = (model or '').strip().lower()
    for prefix, name in (
        ('claude/', 'claude'),
        ('codex/', 'codex'),
        ('cursor/', 'cursor'),
        ('grok', 'grok'),
        ('ollama-local/', 'ollama-local'),
        ('ollama/', 'ollama-local'),
    ):
        if m.startswith(prefix) or prefix.rstrip('/') in m:
            return name
    return a or 'keeproute'


def _dedupe_key(source: str, agent: str, prompt: str) -> str:
    raw = f'{source}|{agent}|{prompt[:800]}'.encode('utf-8', errors='replace')
    return hashlib.sha256(raw).hexdigest()[:24]


def _seen_recently(key: str) -> bool:
    now = time.time()
    with _dedupe_lock:
        dead = [k for k, ts in _recent.items() if now - ts > _DEDUPE_TTL_S]
        for k in dead:
            _recent.pop(k, None)
        if key in _recent:
            return True
        _recent[key] = now
        return False


def _records_path(layout: StateLayout):
    return layout.user_learning / 'route_records.json'


def _traces_path(layout: StateLayout):
    return layout.user_learning / 'intelligence_traces.jsonl'


def _sessions_path(layout: StateLayout):
    return layout.user_learning / 'keeproute_sessions.jsonl'


def record_resolution(
    *,
    problem: str,
    action_taken: str,
    result: str,
    success: bool = True,
    domain: str = 'keeproute',
    tags: Optional[list] = None,
    commands: Optional[list] = None,
    chain_id: str = '',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Append one operational resolution into the global route-learning pool."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    record_id = f'rec_{uuid.uuid4().hex[:12]}'
    conf = 0.72 if success else 0.28
    row = {
        'record_id': record_id,
        'ts': time.time(),
        'problem': _clip(problem, 400),
        'action_taken': _clip(action_taken, 240),
        'result': _clip(result, 2000),
        'success': bool(success),
        'confidence': conf,
        'context': {
            'domain': domain or 'keeproute',
            'tags': list(tags or []),
            'commands': list(commands or []),
            'chain_id': chain_id or '',
        },
    }

    def _mut(data):
        data = data or {'schema_version': 1, 'records': []}
        recs = list(data.get('records') or [])
        recs.append(row)
        data['records'] = recs[-2000:]
        data['schema_version'] = 1
        data['updated_at'] = time.time()
        return data

    update_json(_records_path(layout), _mut, default={'schema_version': 1, 'records': []})
    return row


def list_records(layout: Optional[StateLayout] = None, *, limit: int = 500) -> list[dict]:
    layout = layout or resolve_layout()
    raw = read_json(_records_path(layout), default={'records': []}) or {}
    recs = raw.get('records') if isinstance(raw, dict) else raw
    if not isinstance(recs, list):
        return []
    return list(recs[-max(1, int(limit)):])


def recommend(
    query: str,
    *,
    layout: Optional[StateLayout] = None,
    limit: int = 5,
) -> list[dict]:
    """Surface matching records from the global pool (tag is not a boundary)."""
    layout = layout or resolve_layout()
    q = (query or '').lower().strip()
    if not q:
        return []
    words = {w for w in q.split() if len(w) >= 3}
    scored: list[tuple[float, dict]] = []
    for rec in list_records(layout, limit=800):
        blob = ' '.join([
            str(rec.get('problem') or ''),
            str(rec.get('action_taken') or ''),
            str(rec.get('result') or ''),
            ' '.join((rec.get('context') or {}).get('tags') or []),
        ]).lower()
        hit = sum(1 for w in words if w in blob)
        if hit:
            conf = float(rec.get('confidence') or 0.5)
            scored.append((hit + conf, rec))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in scored[:limit]]


def ingest_keeproute_exchange(
    *,
    prompt: str,
    response: str = '',
    agent: str = '',
    model: str = '',
    source: str = 'keeproute',
    mission_id: str = '',
    success: bool = True,
    error: str = '',
    classification: str = '',
    paid_or_local: str = '',
    extra: Optional[dict] = None,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Record one KeepRoute/OmniRoute exchange into layered intelligence."""
    out: dict[str, Any] = {'ok': False, 'skipped': False}
    try:
        layout = layout or resolve_layout()
        layout.ensure_user_dirs()
        prompt = (prompt or '').strip()
        response = (response or '').strip()
        if not prompt:
            out['error'] = 'prompt required'
            return out
        if len(prompt) < 2 or prompt.lower() in ('hi', 'ok', 'ping', 'health'):
            if len(response) < 8:
                out['ok'] = True
                out['skipped'] = True
                out['reason'] = 'trivial_probe'
                return out

        agent_n = _norm_agent(agent, model)
        source_n = (source or 'keeproute').strip().lower()
        dkey = _dedupe_key(source_n, agent_n, prompt)
        if _seen_recently(dkey):
            out['ok'] = True
            out['skipped'] = True
            out['reason'] = 'deduped'
            return out

        session_id = f'kr_{uuid.uuid4().hex[:12]}'
        tags = list({
            t for t in [
                'keeproute',
                'omniroute',
                'layered-intelligence',
                source_n,
                agent_n,
                (classification or '').strip().lower() or None,
                paid_or_local or None,
            ] if t
        })

        append_jsonl(_sessions_path(layout), {
            'session_id': session_id,
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'source': source_n,
            'agent': agent_n,
            'model': model or None,
            'mission_id': mission_id or None,
            'success': bool(success),
            'classification': classification or None,
            'paid_or_local': paid_or_local or None,
            'prompt': _clip(prompt, 8000),
            'response': _clip(response, 12000),
            'error': _clip(error, 1000) if error else None,
            'extra': extra or {},
        })

        record = record_resolution(
            problem=f'[{source_n}/{agent_n}] {_clip(prompt, 240)}',
            action_taken=(
                f'Routed via {source_n} → {agent_n}'
                + (f' ({model})' if model else '')
            ),
            result=_clip(response or error or '(no response)', 2000),
            success=bool(success) and not error,
            domain='keeproute',
            tags=tags,
            commands=[f'keeproute:{source_n}:{agent_n}'],
            chain_id=mission_id or session_id,
            layout=layout,
        )
        out['record_id'] = record.get('record_id')

        conf = 0.75 if success and not error else 0.25
        append_jsonl(_traces_path(layout), {
            'ts': time.time(),
            'entity_id': f'keeproute:{agent_n}',
            'category': 'keeproute_exchange',
            'sub_category': classification or source_n,
            'route_taken': f'{source_n}/{agent_n}',
            'truth_source': (
                'external_provider' if paid_or_local == 'paid' else 'local_or_omniroute'
            ),
            'confidence': conf,
            'response_len': len(response or ''),
            'avoided_external': paid_or_local == 'local',
            'matched_marker': 'keeproute_ingest',
            'raw_query_len': len(prompt),
            'notes': {
                'source': source_n,
                'model': model,
                'mission_id': mission_id,
                'session_id': session_id,
                'paid_or_local': paid_or_local,
            },
        })
        out['trace'] = True
        out['ok'] = True
        out['session_id'] = session_id
        # Invalidate world-model cache so next REX tick sees fresh signal.
        try:
            from expansion.world_model import invalidate_world_model
            invalidate_world_model()
        except Exception:
            pass
        return out
    except Exception as exc:
        out['error'] = str(exc)
        return out


def pool_summary(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    layout = layout or resolve_layout()
    recs = list_records(layout, limit=2000)
    ok_n = sum(1 for r in recs if r.get('success'))
    fail_n = len(recs) - ok_n
    traces_path = _traces_path(layout)
    trace_n = 0
    if traces_path.is_file():
        try:
            trace_n = sum(1 for _ in traces_path.open(encoding='utf-8') if _.strip())
        except OSError:
            trace_n = 0
    return {
        'global_pool': True,
        'records': len(recs),
        'successes': ok_n,
        'failures': fail_n,
        'traces': trace_n,
        'path': str(layout.user_learning),
    }
