"""Autonomous web / docs / GitHub research tools."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

USER_AGENT = 'OtaconsKeep-ExpansionAutonomy/0.4 (+local research; policy-gated)'
# Browser-ish UA for HTML search fallbacks that 403 bare bots.
HTML_USER_AGENT = (
    'Mozilla/5.0 (compatible; OtaconsKeep-ExpansionAutonomy/0.4; '
    '+https://otaconskeep.github.io)'
)
MAX_BYTES = 400_000
TIMEOUT = 20


def _open(url: str, *, timeout: int = TIMEOUT, user_agent: str = USER_AGENT,
          data: bytes | None = None) -> tuple[str, str]:
    if not url.startswith(('http://', 'https://')):
        raise ValueError('only http(s) URLs allowed')
    headers = {'User-Agent': user_agent, 'Accept': '*/*'}
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=data, headers=headers)
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


def _unwrap_ddg_href(href: str) -> str:
    """Decode DuckDuckGo redirect wrappers to the destination URL."""
    h = (href or '').strip()
    if not h:
        return ''
    if 'uddg=' in h:
        try:
            parsed = urllib.parse.urlparse(h)
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get('uddg'):
                return urllib.parse.unquote(qs['uddg'][0])
        except Exception:
            pass
    if h.startswith('//'):
        return 'https:' + h
    return h


def _from_instant_answer(payload: dict, q: str) -> list[dict]:
    results: list[dict] = []
    abstract = (payload.get('AbstractText') or '').strip()
    abs_url = (payload.get('AbstractURL') or '').strip()
    if abstract:
        results.append({
            'title': payload.get('Heading') or q,
            'url': abs_url,
            'snippet': abstract[:500],
        })
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
    return results


def _from_html_search(query: str) -> list[dict]:
    """DuckDuckGo HTML POST — general web results (Instant Answer is encyclopedic-only)."""
    body = urllib.parse.urlencode({'q': query, 'b': ''}).encode()
    text, _ = _open(
        'https://html.duckduckgo.com/html/',
        user_agent=HTML_USER_AGENT,
        data=body,
    )
    results: list[dict] = []
    # Pair result title links with nearby snippets when present.
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'(?:[\s\S]*?class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>)?',
        text,
        re.I,
    ):
        url = _unwrap_ddg_href(m.group(1))
        title = re.sub(r'<[^>]+>', '', m.group(2) or '').strip()
        snippet = re.sub(r'<[^>]+>', '', m.group(3) or '').strip() if m.lastindex and m.lastindex >= 3 else ''
        if not title and not url:
            continue
        results.append({
            'title': title[:120] or url,
            'url': url,
            'snippet': (snippet or title)[:400],
        })
        if len(results) >= 10:
            break
    return results


def web_search(query: str) -> tuple[dict, str]:
    q = (query or '').strip()
    if not q:
        raise ValueError('query required')
    results: list[dict] = []
    source = 'duckduckgo_instant'

    # 1) Instant Answer — good for encyclopedic queries, often empty for commercial/trend.
    try:
        url = 'https://api.duckduckgo.com/?' + urllib.parse.urlencode({
            'q': q, 'format': 'json', 'no_html': 1, 'skip_disambig': 1,
        })
        text, _ = _open(url)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        results = _from_instant_answer(payload, q)
    except Exception:
        payload = {}
        results = []

    # 2) HTML general-web fallback when Instant Answer returns nothing.
    if not results:
        try:
            results = _from_html_search(q)
            source = 'duckduckgo_html'
        except Exception as exc:
            return {
                'query': q,
                'results': [],
                'source': source,
                'ok': False,
                'error': f'search providers returned 0 hits ({exc})',
            }, f'search({q!r}) → 0 hits'

    if not results:
        return {
            'query': q,
            'results': [],
            'source': source,
            'ok': False,
            'error': 'no search hits',
        }, f'search({q!r}) → 0 hits'

    return {
        'query': q,
        'results': results[:10],
        'source': source,
        'ok': True,
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
