"""Research deliverable synthesis — topics, chrome filter, body extract, optional LLM."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from expansion.state_layout import StateLayout

# Explicit chrome / nav tokens (substring match on lowered text).
_CHROME_TOKENS = (
    'login', 'sign up', 'sign in', 'cart', 'checkout', 'cookie', 'privacy policy',
    'terms of service', 'upgrade to pro', 'mockups', 'fee calculator', 'royalty',
    'add to cart', 'wishlist', 'newsletter', 'subscribe', 'accept cookies',
    'skip to content', 'how it works', 'resource center', 'start selling',
    'catalog pricing', 'print on demand 101', 'dtf database', 'suppliers printers',
    'custom t-shirts', 'custom hoodies', 'home suppliers', 'learn blog about',
)
_NAV_PHRASE = re.compile(
    r'\b(?:skip to content|how it works|resource center|start selling|'
    r'catalog pricing|print on demand|custom t-shirts|custom hoodies|'
    r'solutions|pricing|blog|about us|contact us)\b',
    re.I,
)
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+|\n+')
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{1,}", re.I)
_NUMBERED = re.compile(r'(?:^|\n)\s*(?:\d+[.)]|[-*•])\s+', re.M)
_CONJ_SPLIT = re.compile(
    r'\s*(?:,\s*and\s+|;\s+|\s+—\s+|\s+–\s+|\band also\b|\bplus\b|\bas well as\b)\s+',
    re.I,
)

# Domain seeds: if the request mentions these, force a topic even without '?'.
_TOPIC_SEEDS = (
    ('trend', 'design trends'),
    ('fee', 'platform fees and costs'),
    ('pricing', 'platform fees and costs'),
    ('cost', 'platform fees and costs'),
    ('competitor', 'competitor strategy'),
    ('competition', 'competitor strategy'),
    ('etsy', 'platform fees and costs'),
    ('printful', 'platform fees and costs'),
    ('printify', 'platform fees and costs'),
    ('laser', 'laser engraver / 3D printer integration'),
    ('3d print', 'laser engraver / 3D printer integration'),
    ('engraver', 'laser engraver / 3D printer integration'),
    ('pod', 'print-on-demand platforms'),
    ('print-on-demand', 'print-on-demand platforms'),
    ('print on demand', 'print-on-demand platforms'),
)


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
    """True when text looks like site chrome / nav, not substantive content."""
    t = (text or '').strip()
    if len(t) < 40:
        return True
    low = t.lower()
    if 'skip to content' in low:
        return True
    hits = sum(1 for tok in _CHROME_TOKENS if tok in low)
    nav_hits = len(_NAV_PHRASE.findall(t))
    # Dense slash-separated menu crumbs
    if low.count('/') >= 3 and (hits >= 1 or nav_hits >= 2):
        return True
    if hits >= 3 or nav_hits >= 3:
        return True
    words = _WORD.findall(low)
    if not words:
        return True
    # Repeated short nav tokens ("How it works How it works")
    for phrase in ('how it works', 'custom t-shirts', 'start selling', 'resource center'):
        if low.count(phrase) >= 2:
            return True
    # High title-case / short-token density without sentence punctuation → menu
    caps = sum(1 for w in t.split() if w[:1].isupper() and len(w) > 1)
    periods = t.count('.') + t.count('?')
    if len(words) >= 12 and caps >= max(8, int(len(words) * 0.55)) and periods <= 1:
        return True
    if words and hits >= 2 and len(words) < 30 and periods == 0:
        return True
    # Very low unique-word ratio (nav spam)
    uniq = len(set(words))
    if len(words) >= 20 and uniq / len(words) < 0.45:
        return True
    return False


def _snippet_score(text: str) -> int:
    t = (text or '').strip()
    if not t or is_chrome_snippet(t):
        return 0
    return min(len(t), 2000)


_STOP = frozenset({
    'a', 'an', 'the', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'what',
    'about', 'how', 'do', 'does', 'is', 'are', 'be', 'this', 'that', 'from', 'into',
    'your', 'our', 'their', 'use', 'using', 'also', 'vs', 'versus',
})


def _stems(words: set[str]) -> set[str]:
    out = set(words)
    for w in words:
        if w.endswith('s') and len(w) > 3:
            out.add(w[:-1])
        if w.endswith('ing') and len(w) > 5:
            out.add(w[:-3])
    return out


def _topic_words(topic: str) -> set[str]:
    raw = set(_WORD.findall((topic or '').lower())) - _STOP
    return _stems(raw)


def extract_passages(body: str, topic: str, *, limit: int = 3, max_chars: int = 420) -> list[str]:
    """Pick sentences from a full page body that overlap the topic and aren't chrome."""
    text = (body or '').strip()
    if not text:
        return []
    head = text[:500]
    if is_chrome_snippet(head) and len(text) > 800:
        text = text[400:]
    sents = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    tw = _topic_words(topic)
    ranked: list[tuple[float, str]] = []
    for s in sents:
        if len(s) < 40 or is_chrome_snippet(s):
            continue
        sw = _stems(set(_WORD.findall(s.lower())) - _STOP)
        if not sw:
            continue
        overlap = len(tw & sw) / max(len(tw), 1) if tw else 0.0
        score = overlap * 4.0 + min(len(s), 400) / 400.0
        if tw and overlap <= 0:
            continue
        ranked.append((score, s[:max_chars]))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    seen = set()
    for _, s in ranked:
        key = s[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    if not out:
        for s in sents:
            if len(s) >= 60 and not is_chrome_snippet(s):
                out.append(s[:max_chars])
                if len(out) >= limit:
                    break
    return out


def dedupe_research_refs(refs: list[dict]) -> list[dict]:
    """One entry per URL — keep richest non-chrome body/snippet."""
    best: dict[str, dict] = {}
    orphan_i = 0
    for raw in refs or []:
        if not isinstance(raw, dict):
            continue
        url = (raw.get('url') or '').strip()
        key = normalize_url(url) or f'_orphan_{orphan_i}'
        if key.startswith('_orphan_'):
            orphan_i += 1
        body = (raw.get('body') or '').strip()
        snip = (raw.get('snippet') or '').strip()
        # Prefer longer stored body for scoring
        content = body if len(body) > len(snip) else snip
        title = (raw.get('title') or '').strip()
        cand = {
            'title': title[:160] or url or 'Untitled',
            'url': url,
            'snippet': snip[:800],
            'body': body[:12000],
            'at': raw.get('at'),
            'by': raw.get('by'),
        }
        prev = best.get(key)
        if prev is None:
            best[key] = cand
            continue
        prev_content = (prev.get('body') or prev.get('snippet') or '')
        if _snippet_score(content) > _snippet_score(prev_content):
            if len(cand['title']) < 12 and len(prev.get('title') or '') >= 12:
                cand['title'] = prev['title']
            # Keep whichever body is longer
            if len(prev.get('body') or '') > len(cand.get('body') or ''):
                cand['body'] = prev['body']
            best[key] = cand
        else:
            if len(cand.get('body') or '') > len(prev.get('body') or ''):
                prev['body'] = cand['body']
            if not prev.get('title') and cand['title']:
                prev['title'] = cand['title']
    out = []
    for ref in best.values():
        content = ref.get('body') or ref.get('snippet') or ''
        if is_chrome_snippet(content) and not (ref.get('title') or '').strip():
            continue
        if is_chrome_snippet(ref.get('snippet') or ''):
            ref = dict(ref)
            ref['snippet'] = ''
        out.append(ref)
    return out


def extract_request_topics(request: str, *, limit: int = 8) -> list[str]:
    """Split a multi-part operator ask into distinct answerable topics."""
    text = (request or '').strip()
    if not text:
        return []
    topics: list[str] = []

    # 1) Explicit questions
    if '?' in text:
        parts = [p.strip() for p in re.split(r'\?\s*', text) if p.strip()]
        for part in parts:
            part = part.strip(' .;,-')
            if len(part) >= 8:
                topics.append(part if part.endswith('?') else part + '?')

    # 2) Numbered / bulleted lines
    if _NUMBERED.search(text):
        chunks = _NUMBERED.split(text)
        for chunk in chunks:
            chunk = chunk.strip(' .;,-')
            if len(chunk) >= 12:
                topics.append(chunk[:240])

    # 3) Conjunction / semicolon splits for long asks without '?'
    if len(topics) <= 1 and len(text) >= 80:
        for part in _CONJ_SPLIT.split(text):
            part = part.strip(' .;,-')
            if len(part) >= 20:
                topics.append(part[:240])

    # 4) Domain seeds — only when not already covered by a question/clause topic
    low = text.lower()
    if len(topics) < 2 or len(text) >= 60:
        for needle, label in _TOPIC_SEEDS:
            if needle not in low:
                continue
            label_words = set(_WORD.findall(label.lower()))
            covered = any(
                len(label_words & set(_WORD.findall(t.lower()))) >= max(1, len(label_words) // 2)
                for t in topics
            )
            if not covered and label not in topics:
                topics.append(label)

    if not topics:
        topics = [text[:200]]

    # If we still have a single mega-topic, force-split on commas for parallel nouns
    if len(topics) == 1 and len(topics[0]) > 100 and ',' in topics[0]:
        forced = [p.strip(' .;,-') for p in topics[0].split(',') if len(p.strip()) >= 16]
        if len(forced) >= 2:
            topics = forced

    seen = set()
    uniq = []
    for t in topics:
        key = re.sub(r'\s+', ' ', t.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t[:240])
        if len(uniq) >= limit:
            break
    return uniq


def _overlap(topic: str, ref: dict) -> float:
    tw = _topic_words(topic)
    if not tw:
        return 0.0
    blob = f"{ref.get('title') or ''} {ref.get('snippet') or ''} {(ref.get('body') or '')[:3000]}".lower()
    rw = _stems(set(_WORD.findall(blob)) - _STOP)
    if not rw:
        return 0.0
    return len(tw & rw) / max(len(tw), 1)


def pick_refs_for_topic(topic: str, refs: list[dict], *, limit: int = 2) -> list[dict]:
    ranked = sorted(
        refs,
        key=lambda r: (
            _overlap(topic, r),
            _snippet_score(r.get('body') or r.get('snippet') or ''),
        ),
        reverse=True,
    )
    out = []
    for r in ranked:
        content = r.get('body') or r.get('snippet') or ''
        if _overlap(topic, r) <= 0 and _snippet_score(content) < 60:
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


def _llm_synthesize(
    request: str,
    topics: list[str],
    refs: list[dict],
) -> Optional[str]:
    """Ask local Ollama to answer each topic from fetched bodies. None if unavailable."""
    if os.environ.get('OTACON_RESEARCH_LLM', '1').strip().lower() in ('0', 'false', 'no', 'off'):
        return None
    # Need at least one body worth reading
    bodies = []
    for r in refs[:5]:
        body = (r.get('body') or r.get('snippet') or '').strip()
        if len(body) < 80 or is_chrome_snippet(body[:200]):
            continue
        bodies.append({
            'title': r.get('title') or '',
            'url': r.get('url') or '',
            'text': body[:3500],
        })
    if not bodies or not topics:
        return None
    try:
        from core.providers import OllamaProvider
    except Exception:
        return None
    endpoint = (
        os.environ.get('OTACON_LLM_ENDPOINT')
        or os.environ.get('OLLAMA_URL')
        or 'http://127.0.0.1:11434'
    )
    requested = os.environ.get('OTACON_LLM_MODEL') or 'qwen2.5:7b'
    try:
        prov = OllamaProvider(endpoint, timeout=int(os.environ.get('OTACON_RESEARCH_LLM_TIMEOUT', '90')))
        model, _note = prov.resolve_model(requested)
        topic_lines = '\n'.join(f'{i}. {t}' for i, t in enumerate(topics, 1))
        src_blocks = []
        for i, b in enumerate(bodies, 1):
            src_blocks.append(
                f"SOURCE {i}: {b['title']}\nURL: {b['url']}\nEXCERPT:\n{b['text']}\n"
            )
        prompt = (
            'You are Ledger, a research analyst. Answer ONLY from the sources below.\n'
            'For each numbered topic, write 2–4 factual sentences with concrete details '
            '(numbers, platform names, mechanisms). If sources lack an answer, say so explicitly.\n'
            'Do NOT invent fees or trends. Do NOT paste navigation menus.\n'
            'Output markdown with one ### heading per topic, then bullets.\n\n'
            f'TOPICS:\n{topic_lines}\n\n'
            f'SOURCES:\n{"".join(src_blocks)}\n'
            'BEGIN ANSWERS:\n'
        )
        text = prov.generate(
            model, prompt,
            options={'temperature': 0.2, 'num_predict': 1400},
        )
        if not text or len(text.strip()) < 80:
            return None
        if is_chrome_snippet(text[:300]):
            return None
        return text.strip()
    except Exception:
        return None


def build_research_markdown(
    *,
    request: str,
    job_id: str,
    agent: str,
    refs: list[dict],
) -> tuple[str, dict[str, Any]]:
    """Return (markdown, meta) with per-topic answers from bodies and/or LLM."""
    cleaned = dedupe_research_refs(refs)
    topics = extract_request_topics(request)
    llm_block = _llm_synthesize(request, topics, cleaned)

    lines = [
        f'# Research plan: {(request or "")[:200]}',
        '',
        f'_Job `{job_id}` · agent `{agent}` · {len(cleaned)} unique source(s) · '
        f'{len(topics)} topic(s)_',
        '',
        '## Answers',
        '',
    ]

    answered_topics = 0
    synthesis_source = 'none'

    if llm_block and '###' in llm_block:
        lines.append(llm_block.rstrip())
        lines.append('')
        answered_topics = max(1, llm_block.count('###'))
        synthesis_source = 'llm'
    else:
        synthesis_source = 'extractive'
        for topic in topics:
            picks = pick_refs_for_topic(topic, cleaned, limit=2)
            lines.append(f'### {topic}')
            topic_hit = False
            for ref in picks:
                body = (ref.get('body') or '').strip()
                snip = (ref.get('snippet') or '').strip()
                passages = extract_passages(body or snip, topic, limit=2)
                title = (ref.get('title') or 'Source').strip()
                url = (ref.get('url') or '').strip()
                if not passages:
                    continue
                topic_hit = True
                for p in passages:
                    bullet = f'- {p}'
                    if url:
                        bullet += f'  \n  _(source: {title} — {url})_'
                    lines.append(bullet)
            if not topic_hit:
                lines.append(
                    '- No sourced passage answered this topic yet '
                    '(fetched pages lacked overlapping non-chrome content).'
                )
            else:
                answered_topics += 1
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
    if synthesis_source == 'llm':
        lines.append(
            '- Answers were drafted by the local research model from fetched page bodies; '
            'verify fees and policies on the live vendor pages before spending money.'
        )
    else:
        lines.append(
            '- Answers are extractive passages from fetched page bodies (not nav chrome). '
            'Verify fees and policies on the live vendor pages before spending money.'
        )
    lines.append(
        f'- Topics covered: {answered_topics}/{len(topics)} '
        f'(synthesis={synthesis_source}).'
    )
    lines.append('')

    # Multi-topic asks must cover more than a catch-all single bucket.
    need = 1 if len(topics) <= 1 else max(2, (len(topics) + 1) // 2)
    synthesis_ok = bool(cleaned) and answered_topics >= need and '## Answers' in '\n'.join(lines)

    meta = {
        'unique_sources': len(cleaned),
        'topics': len(topics),
        'answered_topics': answered_topics,
        'answered_bullets': answered_topics,  # back-compat for older callers
        'synthesis_ok': synthesis_ok,
        'synthesis_source': synthesis_source,
        'topics_list': topics,
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
