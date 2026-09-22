"""Research deliverable synthesis — dedupe sources, answer the request, optional desktop export."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from expansion.state_layout import StateLayout

# Nav / chrome tokens that dominate bad fetch snippets.
_CHROME_TOKENS = (
    'login', 'sign up', 'sign in', 'cart', 'checkout', 'cookie', 'privacy policy',
    'terms of service', 'upgrade to pro', 'mockups', 'fee calculator', 'royalty',
    'add to cart', 'wishlist', 'newsletter', 'subscribe', 'accept cookies',
)
_QUESTION_SPLIT = re.compile(r'[?;\n]+|\s+[—–-]\s+|\s{2,}')
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{1,}", re.I)


def normalize_url(url: str) -> str:
    u = (url or '').strip()
    if not u:
        return ''
    try:
        p = urlparse(u)
        host = (p.netloc or '').lower().removeprefix('www.')
        path = (p.path or '/').rstrip('/') or '/'
        return f'{host}{path}'
    except Exception:
        return u.lower()


def is_chrome_snippet(text: str) -> bool:
    """True when a snippet looks like site chrome / nav, not substantive content."""
    t = (text or '').strip()
    if len(t) < 40:
        return True
    low = t.lower()
    hits = sum(1 for tok in _CHROME_TOKENS if tok in low)
    # Dense slash-separated menu crumbs
    if low.count('/') >= 4 and hits >= 1:
        return True
    if hits >= 3:
        return True
    words = _WORD.findall(low)
    if words and hits >= 2 and len(words) < 25:
        return True
    return False


def _snippet_score(text: str) -> int:
    t = (text or '').strip()
    if not t or is_chrome_snippet(t):
        return 0
    return min(len(t), 800)


def dedupe_research_refs(refs: list[dict]) -> list[dict]:
    """One entry per URL — keep the richest non-chrome snippet."""
    best: dict[str, dict] = {}
    orphan_i = 0
    for raw in refs or []:
        if not isinstance(raw, dict):
            continue
        url = (raw.get('url') or '').strip()
        key = normalize_url(url) or f'_orphan_{orphan_i}'
        if key.startswith('_orphan_'):
            orphan_i += 1
        snip = (raw.get('snippet') or '').strip()
        title = (raw.get('title') or '').strip()
        cand = {
            'title': title[:160] or url or 'Untitled',
            'url': url,
            'snippet': snip[:800],
            'at': raw.get('at'),
            'by': raw.get('by'),
        }
        prev = best.get(key)
        if prev is None:
            best[key] = cand
            continue
        if _snippet_score(cand['snippet']) > _snippet_score(prev.get('snippet') or ''):
            if len(cand['title']) < 12 and len(prev.get('title') or '') >= 12:
                cand['title'] = prev['title']
            best[key] = cand
        elif not prev.get('title') and cand['title']:
            prev['title'] = cand['title']
    out = []
    for ref in best.values():
        if is_chrome_snippet(ref.get('snippet') or '') and not (ref.get('title') or '').strip():
            continue
        if is_chrome_snippet(ref.get('snippet') or ''):
            ref = dict(ref)
            ref['snippet'] = ''
        out.append(ref)
    return out


def extract_request_topics(request: str, *, limit: int = 6) -> list[str]:
    """Split the operator request into answerable topic lines."""
    text = (request or '').strip()
    if not text:
        return []
    qmarks = [p.strip() for p in re.split(r'\?\s*', text) if p.strip()]
    topics: list[str] = []
    if text.count('?') >= 1 and len(qmarks) >= 1:
        for part in qmarks:
            part = part.strip(' .;,-')
            if len(part) >= 8:
                topics.append(part if part.endswith('?') else part + '?')
    if not topics:
        for part in _QUESTION_SPLIT.split(text):
            part = part.strip(' .;,-')
            if len(part) >= 12:
                topics.append(part)
    if not topics:
        topics = [text[:200]]
    seen = set()
    uniq = []
    for t in topics:
        key = t.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t[:240])
        if len(uniq) >= limit:
            break
    return uniq


def _overlap(topic: str, ref: dict) -> float:
    tw = set(_WORD.findall((topic or '').lower()))
    if not tw:
        return 0.0
    blob = f"{ref.get('title') or ''} {ref.get('snippet') or ''}".lower()
    rw = set(_WORD.findall(blob))
    if not rw:
        return 0.0
    return len(tw & rw) / max(len(tw), 1)


def pick_refs_for_topic(topic: str, refs: list[dict], *, limit: int = 2) -> list[dict]:
    ranked = sorted(
        refs,
        key=lambda r: (_overlap(topic, r), _snippet_score(r.get('snippet') or '')),
        reverse=True,
    )
    out = []
    for r in ranked:
        if _overlap(topic, r) <= 0 and _snippet_score(r.get('snippet') or '') < 60:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    if not out and ranked:
        out = ranked[:1]
    return out


def resolve_user_desktop() -> Optional[Path]:
    """Best-effort writable Desktop (OneDrive-aware under WSL). Opt-in callers only."""
    override = (os.environ.get('OTACON_DESKTOP_DIR') or '').strip()
    if override:
        p = Path(override).expanduser()
        if p.is_dir() and os.access(p, os.W_OK):
            return p
    names: list[str] = []
    for key in ('OTACON_WIN_USER', 'WSL_USER'):
        v = (os.environ.get(key) or '').strip()
        if v:
            names.append(v)
    home_name = Path.home().name
    if home_name and home_name not in names:
        names.append(home_name)
    up = (os.environ.get('USERPROFILE') or '').strip()
    if up:
        m = re.match(r'^[A-Za-z]:\\Users\\([^\\/]+)', up)
        if m and m.group(1) not in names:
            names.insert(0, m.group(1))
    for name in names:
        for rel in (
            f'/mnt/c/Users/{name}/OneDrive/Desktop',
            f'/mnt/c/Users/{name}/Desktop',
        ):
            p = Path(rel)
            try:
                if p.is_dir() and os.access(p, os.W_OK):
                    return p
            except OSError:
                continue
    return None


def maybe_export_to_desktop(
    src: Path,
    *,
    layout: StateLayout,
    enabled: bool | None = None,
) -> Optional[str]:
    """Copy deliverable to Desktop when pref/env enables it. Never default-on."""
    if enabled is None:
        try:
            from expansion.launchpad import load_prefs
            prefs = load_prefs(layout)
            enabled = bool(prefs.get('export_deliverables_to_desktop'))
        except Exception:
            enabled = False
        env = (os.environ.get('OTACON_EXPORT_DELIVERABLES_DESKTOP') or '').strip().lower()
        if env in ('1', 'true', 'yes', 'on'):
            enabled = True
    if not enabled:
        return None
    desk = resolve_user_desktop()
    if not desk:
        return None
    try:
        dest = desk / src.name
        shutil.copy2(src, dest)
        return str(dest)
    except OSError:
        return None


def build_research_markdown(
    *,
    request: str,
    job_id: str,
    agent: str,
    refs: list[dict],
) -> tuple[str, dict[str, Any]]:
    """Return (markdown, meta) with answers mapped to the request topics."""
    cleaned = dedupe_research_refs(refs)
    topics = extract_request_topics(request)
    lines = [
        f'# Research plan: {(request or "")[:200]}',
        '',
        f'_Job `{job_id}` · agent `{agent}` · {len(cleaned)} unique source(s)_',
        '',
        '## Answers',
        '',
    ]
    answered = 0
    for topic in topics:
        picks = pick_refs_for_topic(topic, cleaned, limit=2)
        lines.append(f'### {topic}')
        if not picks:
            lines.append('- No sourced finding matched this topic yet.')
            lines.append('')
            continue
        for ref in picks:
            title = (ref.get('title') or 'Source').strip()
            url = (ref.get('url') or '').strip()
            snip = (ref.get('snippet') or '').strip()
            if is_chrome_snippet(snip):
                snip = ''
            bullet = f'- **{title}**'
            if url:
                bullet += f' — {url}'
            lines.append(bullet)
            if snip:
                lines.append(f'  - {snip[:420]}')
                answered += 1
            elif url:
                lines.append('  - (title/URL retained; page body was site chrome)')
        lines.append('')

    lines.append('## Sources')
    lines.append('')
    if not cleaned:
        lines.append('- None.')
    else:
        for i, ref in enumerate(cleaned[:12], 1):
            title = (ref.get('title') or 'Untitled').strip()
            url = (ref.get('url') or '').strip()
            lines.append(f'{i}. {title}' + (f' — {url}' if url else ''))
    lines.append('')
    lines.append('## Caveats')
    lines.append('')
    lines.append(
        '- Findings are extracted from policy-gated web.search / web.fetch snippets; '
        'verify fees and policies on the live vendor pages before spending money.'
    )
    lines.append(
        '- Prefer the Answers section over raw page chrome; navigation menus are filtered out.'
    )
    lines.append('')

    meta = {
        'unique_sources': len(cleaned),
        'topics': len(topics),
        'answered_bullets': answered,
        'synthesis_ok': bool(cleaned) and answered > 0,
    }
    return '\n'.join(lines), meta


def write_research_deliverable(
    layout: StateLayout,
    *,
    job_id: str,
    request: str,
    agent: str,
    refs: list[dict],
) -> Optional[dict[str, Any]]:
    """Write jobs/deliverables/{job_id}.md; optional desktop copy. Returns paths/meta."""
    if not refs:
        return None
    body, meta = build_research_markdown(
        request=request, job_id=job_id, agent=agent, refs=refs,
    )
    out_dir = layout.user_jobs / 'deliverables'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{job_id}.md'
    path.write_text(body, encoding='utf-8')
    desktop = maybe_export_to_desktop(path, layout=layout)
    return {
        'path': str(path),
        'desktop_path': desktop or '',
        'body': body,
        **meta,
    }
