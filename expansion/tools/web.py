"""Autonomous web / docs / GitHub research tools."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

USER_AGENT = 'OtaconsKeep-ExpansionAutonomy/0.4 (+local research; policy-gated)'
MAX_BYTES = 400_000
TIMEOUT = 20


def _open(url: str, *, timeout: int = TIMEOUT) -> tuple[str, str]:
    if not url.startswith(('http://', 'https://')):
        raise ValueError('only http(s) URLs allowed')
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — intentional tool
        ctype = (resp.headers.get('Content-Type') or '')[:80]
        raw = resp.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raw = raw[:MAX_BYTES]
        try:
            text = raw.decode('utf-8', errors='replace')
        except Exception:
            text = raw.decode('latin-1', errors='replace')
        return text, ctype


def web_search(query: str) -> tuple[dict, str]:
    q = (query or '').strip()
    if not q:
        raise ValueError('query required')
    # DuckDuckGo Instant Answer API — no key, suitable for autonomous R&D.
    url = 'https://api.duckduckgo.com/?' + urllib.parse.urlencode({
        'q': q, 'format': 'json', 'no_html': 1, 'skip_disambig': 1,
    })
    text, _ = _open(url)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}
    results = []
    abstract = (payload.get('AbstractText') or '').strip()
    abs_url = (payload.get('AbstractURL') or '').strip()
    if abstract:
        results.append({'title': payload.get('Heading') or q, 'url': abs_url, 'snippet': abstract[:500]})
    for topic in (payload.get('RelatedTopics') or [])[:8]:
        if isinstance(topic, dict) and topic.get('Text'):
            results.append({
                'title': (topic.get('Text') or '')[:80],
                'url': topic.get('FirstURL') or '',
                'snippet': (topic.get('Text') or '')[:400],
            })
        elif isinstance(topic, dict) and topic.get('Topics'):
            for sub in topic['Topics'][:3]:
                if sub.get('Text'):
                    results.append({
                        'title': (sub.get('Text') or '')[:80],
                        'url': sub.get('FirstURL') or '',
                        'snippet': (sub.get('Text') or '')[:400],
                    })
    return {
        'query': q,
        'results': results[:10],
        'source': 'duckduckgo_instant',
    }, f'search({q!r}) → {len(results)} hits'


def web_fetch(url: str) -> tuple[dict, str]:
    u = (url or '').strip()
    if not u:
        raise ValueError('url required')
    text, ctype = _open(u)
    # Strip tags lightly for research snippets
    plain = re.sub(r'<script[\s\S]*?</script>', ' ', text, flags=re.I)
    plain = re.sub(r'<style[\s\S]*?</style>', ' ', plain, flags=re.I)
    plain = re.sub(r'<[^>]+>', ' ', plain)
    plain = re.sub(r'\s+', ' ', plain).strip()
    return {
        'url': u,
        'content_type': ctype,
        'length': len(text),
        'snippet': plain[:2000],
        'title_guess': (plain[:80] if plain else u),
    }, f'fetch {u} ({len(text)} bytes)'


def github_read(url_or_path: str) -> tuple[dict, str]:
    raw = (url_or_path or '').strip()
    if not raw:
        raise ValueError('url or path required')
    if raw.startswith('http://') or raw.startswith('https://'):
        # Prefer raw content for blobs
        u = raw.replace('github.com/', 'raw.githubusercontent.com/').replace('/blob/', '/')
        if 'github.com' in raw and '/blob/' not in raw and 'raw.githubusercontent' not in u:
            # API-ish fallback — fetch page
            u = raw
        return web_fetch(u)
    # owner/repo/path → raw github
    parts = raw.strip('/').split('/')
    if len(parts) >= 3:
        owner, repo, *rest = parts
        u = f'https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{"/".join(rest)}'
        return web_fetch(u)
    raise ValueError('expected URL or owner/repo/path')
