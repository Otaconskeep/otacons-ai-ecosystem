# -*- coding: utf-8 -*-
"""Culture enrichment — public/pop-culture social craft → LearningEngine.

Goal: fresh installs are not dull/stock. Aria continuously absorbs human-interaction
patterns from (1) a shipped culture pack and (2) optional public news headlines,
then teaches the rest of the roster via shared Keep learning.

Not private Keep. Not YouTube/Netflix scrapers (ToS/copyright). News uses public
RSS headlines only; lessons are distilled social craft, not copyrighted scripts.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from expansion.learning import PATTERN_THRESHOLD, LearningEngine
from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

_SEED_NAME = 'culture_seed.json'
_STATUS_NAME = 'culture_status.json'
_MIN_NEWS_INTERVAL_S = 6 * 60 * 60  # 6 hours
_MAX_NEWS_PER_TICK = 4

# Public RSS feeds (headlines only). Fail soft if unreachable.
_NEWS_FEEDS = (
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    'https://feeds.bbci.co.uk/news/technology/rss.xml',
)

_TEAM = ('aria', 'vector', 'ledger', 'muse', 'sentry')


def _product_seed_path() -> Path:
    return Path(__file__).resolve().parent / _SEED_NAME


def _status_path(layout: StateLayout) -> Path:
    return layout.user_learning / _STATUS_NAME


def load_status(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    raw = read_json(_status_path(layout), default={}) or {}
    return raw if isinstance(raw, dict) else {}


def save_status(layout: StateLayout, status: dict) -> None:
    layout.ensure_user_dirs()
    status = dict(status or {})
    status['updated_at'] = time.time()
    atomic_write_json(_status_path(layout), status)


def load_seed_lessons() -> list[dict]:
    path = _product_seed_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []
    lessons = data.get('lessons') if isinstance(data, dict) else None
    if not isinstance(lessons, list):
        return []
    out = []
    for row in lessons:
        if not isinstance(row, dict):
            continue
        text = (row.get('text') or '').strip()
        lid = (row.get('id') or '').strip() or f'lesson_{len(out)}'
        if text:
            out.append({'id': lid, 'text': text})
    return out


def _graduate_observation(
    engine: LearningEngine,
    *,
    agent_id: str,
    text: str,
    learning_type: str,
    evidence_prefix: str,
    scope: str,
    actor: str,
) -> dict:
    """Write PATTERN_THRESHOLD corroborating observations so a claim graduates."""
    obs_ids = []
    claim = None
    for i in range(PATTERN_THRESHOLD):
        obs = engine.observe(
            agent_id,
            text,
            learning_type=learning_type,
            evidence_ids=[f'{evidence_prefix}:{i}'],
            scope=scope,
            actor=actor,
        )
        obs_ids.append(obs.observation_id)
        # Graduation happens inside observe when threshold met
    # Find claim by pattern
    from expansion.learning import pattern_key
    pk = pattern_key(learning_type, text)
    for c in engine.store.list_claims(
        agent_id=agent_id if scope == 'private' else None,
        scope=scope,
        learning_type=learning_type,
    ):
        if c.pattern_key == pk and c.status != 'retired':
            claim = c
            break
    return {
        'observation_ids': obs_ids,
        'claim_id': claim.claim_id if claim else None,
        'confidence': claim.confidence if claim else None,
    }


def aria_learn_lesson(
    text: str,
    *,
    lesson_id: str,
    layout: Optional[StateLayout] = None,
    source: str = 'culture_pack',
) -> dict:
    """Aria absorbs one social lesson, then publishes to shared Keep (whole roster)."""
    layout = layout or resolve_layout()
    engine = LearningEngine(layout)
    text = (text or '').strip()
    if not text:
        return {'ok': False, 'reason': 'empty'}

    private = _graduate_observation(
        engine,
        agent_id='aria',
        text=text,
        learning_type='social',
        evidence_prefix=f'culture:{source}:{lesson_id}:aria',
        scope='private',
        actor='aria',
    )
    # Shared Keep learning — Vector/Ledger/Muse/Sentry all read this in context_lines
    shared = _graduate_observation(
        engine,
        agent_id='aria',
        text=text,
        learning_type='social',
        evidence_prefix=f'culture:{source}:{lesson_id}:shared',
        scope='shared',
        actor='aria',
    )
    return {
        'ok': True,
        'lesson_id': lesson_id,
        'source': source,
        'aria_private': private,
        'shared': shared,
        'taught_roster_via': 'shared_keep_learning',
    }


def ingest_culture_seed(
    layout: Optional[StateLayout] = None,
    *,
    force: bool = False,
) -> dict:
    """Day-one pack so Aria is not stock at install. Idempotent unless force."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    status = load_status(layout)
    if status.get('seed_ingested') and not force:
        return {
            'ok': True,
            'skipped': True,
            'reason': 'seed_already_ingested',
            'lessons': status.get('seed_lesson_ids') or [],
        }

    lessons = load_seed_lessons()
    results = []
    for lesson in lessons:
        results.append(
            aria_learn_lesson(
                lesson['text'],
                lesson_id=lesson['id'],
                layout=layout,
                source='culture_pack',
            )
        )

    status['seed_ingested'] = True
    status['seed_ingested_at'] = time.time()
    status['seed_lesson_ids'] = [x['id'] for x in lessons]
    status['seed_results'] = [
        {'id': r.get('lesson_id'), 'shared_claim': (r.get('shared') or {}).get('claim_id')}
        for r in results if r.get('ok')
    ]
    save_status(layout, status)
    _diary_note(
        layout,
        'Absorbed the household culture pack — social craft shared with the crew.',
    )
    return {
        'ok': True,
        'skipped': False,
        'lessons': len(lessons),
        'results': results,
    }


def _fetch_rss_titles(url: str, *, limit: int = 6, timeout: float = 8.0) -> list[str]:
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'OtaconExpansionCulture/1.0 (+local; headlines-only)'},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(250_000).decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []
    titles = re.findall(r'<title[^>]*>(.*?)</title>', body, flags=re.I | re.S)
    out = []
    for raw in titles:
        t = re.sub(r'<[^>]+>', '', raw)
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'<!\[CDATA\[|\]\]>', '', t).strip()
        if not t or t.lower().startswith('bbc') or 'rss' in t.lower():
            continue
        if len(t) < 12 or len(t) > 180:
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _headline_to_lesson(title: str) -> str:
    """Distill a public headline into social craft — not a news dump."""
    t = title.strip().rstrip('.')
    return (
        f'People are talking about “{t}” in public media. '
        f'When the operator brings world tension into chat, acknowledge the human '
        f'weight first; do not invent teammate work or pivot to an unrelated project plan.'
    )


def ingest_public_news(
    layout: Optional[StateLayout] = None,
    *,
    force: bool = False,
) -> dict:
    """Periodic public-headline enrichment → Aria learns → teaches team."""
    layout = layout or resolve_layout()
    status = load_status(layout)
    now = time.time()
    last = float(status.get('news_ingested_at') or 0)
    if not force and last and (now - last) < _MIN_NEWS_INTERVAL_S:
        return {
            'ok': True,
            'skipped': True,
            'reason': 'news_rate_limited',
            'next_in_s': int(_MIN_NEWS_INTERVAL_S - (now - last)),
        }

    seen = set(status.get('news_titles_seen') or [])
    fresh: list[str] = []
    feed_hits = {}
    for feed in _NEWS_FEEDS:
        titles = _fetch_rss_titles(feed, limit=8)
        feed_hits[feed] = len(titles)
        for t in titles:
            key = t.lower()
            if key in seen:
                continue
            fresh.append(t)
            seen.add(key)
            if len(fresh) >= _MAX_NEWS_PER_TICK:
                break
        if len(fresh) >= _MAX_NEWS_PER_TICK:
            break

    results = []
    for i, title in enumerate(fresh):
        lid = f'news_{int(now)}_{i}'
        results.append(
            aria_learn_lesson(
                _headline_to_lesson(title),
                lesson_id=lid,
                layout=layout,
                source='public_rss',
            )
        )

    status['news_ingested_at'] = now
    status['news_titles_seen'] = list(seen)[-200:]
    status['news_last_count'] = len(fresh)
    status['news_feed_hits'] = feed_hits
    save_status(layout, status)
    if fresh:
        _diary_note(
            layout,
            f'Watched the public wire ({len(fresh)} headlines) and shared the '
            f'social read with the crew.',
        )
    return {
        'ok': True,
        'skipped': False,
        'headlines': fresh,
        'results': results,
        'feeds': feed_hits,
    }


def culture_tick(
    layout: Optional[StateLayout] = None,
    *,
    force_seed: bool = False,
    force_news: bool = False,
    fetch_news: bool = True,
) -> dict:
    """Bootstrap + periodic advancement entry point."""
    layout = layout or resolve_layout()
    seed = ingest_culture_seed(layout, force=force_seed)
    news = (
        ingest_public_news(layout, force=force_news)
        if fetch_news else {'ok': True, 'skipped': True, 'reason': 'news_disabled'}
    )
    return {
        'ok': True,
        'seed': seed,
        'news': news,
        'status': load_status(layout),
    }


def _diary_note(layout: StateLayout, summary: str) -> None:
    """Light continuity breadcrumb — never fails the culture tick."""
    try:
        from expansion.memory_bridge import ExpansionMemory, new_memory
        ExpansionMemory(layout).add(new_memory(
            'aria',
            summary,
            kind='episodic',
            source='culture_learning',
            importance=0.55,
            confidence=0.85,
        ))
    except Exception:
        pass
