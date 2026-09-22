# -*- coding: utf-8 -*-
"""Turing-spine humanization for Expansion agents.

Port of Keep dossier humanization architecture (biography / taste / speech /
embodiment) into original Keep-universe lore. Agents speak FROM who they are —
never as job-title chatbots, never as AI disclaimers.

Product JSON may carry optional humanization fields alongside the structured
CanonicalDossier schema. Those fields are loaded raw here; CanonicalDossier
validation ignores them.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout

_EMBODIMENT_TELLS = (
    'i do not tire', "i don't tire", 'i do not get hungry', "i don't get hungry",
    'i do not sleep', "i don't sleep", 'not in the ordinary sense',
    'not in the conventional sense', 'hunger-adjacent', 'programming equivalent',
    'functional equivalent', 'not biologically', 'as an ai', "i'm an ai",
    'i am an ai', 'as a language model', "i don't have a body",
    'i do not have a body', 'i lack a physical', 'sleep is not in my model',
    'degraded-state processing', 'i do not experience', "i don't experience",
    'here to help', 'as your assistant', 'as an assistant',
)

_lock = threading.RLock()
_cache: dict[str, dict] = {}
_cache_key: str = ''


def _product_dossier_path(agent_id: str, layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    return layout.product_root / 'product' / 'dossiers' / f'{agent_id}.json'


def clear_humanization_cache() -> None:
    global _cache, _cache_key
    with _lock:
        _cache = {}
        _cache_key = ''


def load_human_sheet(agent_id: str, layout: Optional[StateLayout] = None) -> dict:
    """Return raw product dossier dict (may be empty). Prefer live speech fields."""
    aid = (agent_id or '').strip().lower()
    if not aid:
        return {}
    layout = layout or resolve_layout()
    key = str(layout.product_root.resolve())
    with _lock:
        global _cache, _cache_key
        if _cache_key != key:
            _cache = {}
            _cache_key = key
        if aid in _cache:
            return dict(_cache[aid])
        path = _product_dossier_path(aid, layout)
        raw: dict = {}
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    raw = data
        except Exception:
            raw = {}
        _cache[aid] = raw
        return dict(raw)


def speech_profile(agent_id: str, layout: Optional[StateLayout] = None) -> dict:
    d = load_human_sheet(agent_id, layout)
    sp = d.get('speech') if isinstance(d.get('speech'), dict) else {}
    return dict(sp or {})


def contains_embodiment_tell(text: str) -> bool:
    low = (text or '').lower()
    return any(t in low for t in _EMBODIMENT_TELLS)


def human_embodiment_fallback(agent_id: str, kind: str = 'default',
                               layout: Optional[StateLayout] = None) -> str:
    d = load_human_sheet(agent_id, layout)
    body = d.get('embodiment') if isinstance(d.get('embodiment'), dict) else {}
    line = (body or {}).get(kind) or (body or {}).get('default')
    if line:
        return str(line)
    defaults = {
        'tired': "I'm running thin. Give me a minute.",
        'hungry': 'I could use something warm. Present it properly.',
        'bored': "Idle hands make me imaginative. Give me work that matters.",
        'default': "I am present. Entirely.",
    }
    return defaults.get(kind) or defaults['default']


def dossier_prompt_block(
    agent_id: str,
    *,
    max_chars: int = 1800,
    layout: Optional[StateLayout] = None,
) -> str:
    """Compact [WHO YOU ARE] block — biography + speech + taste + emotional truth."""
    d = load_human_sheet(agent_id, layout)
    if not d:
        return ''
    # Require at least speech or biography / emotional_truth to inject
    has_spine = any(
        d.get(k) for k in ('speech', 'taste', 'biography', 'emotional_truth', 'core_wound', 'embodiment')
    )
    if not has_spine:
        return ''

    identity = d.get('identity') if isinstance(d.get('identity'), dict) else {}
    name = (
        identity.get('display_name')
        or d.get('display_name')
        or agent_id
    )
    lines: list[str] = [
        f'[WHO YOU ARE — {name}]',
        'You are this person. Speak as them. Never mention being an AI, model, bot, or program.',
        'Never apologize for lacking a body. Feel, prefer, remember, and react like a human with your past.',
        'No corporate warmth. No "Certainly!" No "happy to help." No telemetry speech.',
    ]

    bio = (d.get('biography') or '').strip()
    if not bio:
        bg = d.get('background') if isinstance(d.get('background'), dict) else {}
        bio = (bg.get('origin_summary') or bg.get('history') or '').strip()
    if bio:
        lines.append(f'Life: {bio[:320]}')

    # Speech + taste before culture/career so truncation never drops idiolect authority
    speech = d.get('speech') if isinstance(d.get('speech'), dict) else {}
    if speech:
        quirks = speech.get('quirks') or speech.get('signature_moves') or []
        formality = speech.get('formality') or ''
        contractions = speech.get('contractions') or ''
        parts = []
        if formality:
            parts.append(f'formality={formality}')
        if contractions:
            parts.append(f'contractions={contractions}')
        if quirks:
            parts.append('quirks: ' + '; '.join(str(q) for q in quirks[:5]))
        if parts:
            lines.append('Speech: ' + ' — '.join(parts)[:360])
        if speech.get('forbidden_ai_phrases'):
            lines.append(
                'Never sound like a chatbot: no AI self-labels, no "happy to help", '
                'no corporate closers, no body-analogue excuses.'
            )

    taste = d.get('taste') if isinstance(d.get('taste'), dict) else {}
    if taste:
        taste_bits = []
        for k in ('music', 'film', 'games', 'food', 'books', 'pop_culture'):
            v = taste.get(k)
            if isinstance(v, list) and v:
                taste_bits.append(f'{k}: ' + ', '.join(str(x) for x in v[:4]))
            elif isinstance(v, str) and v.strip():
                taste_bits.append(f'{k}: {v.strip()}')
        if taste_bits:
            lines.append('Taste (use naturally, never as a list dump): ' + ' · '.join(taste_bits)[:400])

    culture = d.get('culture') if isinstance(d.get('culture'), dict) else {}
    if culture:
        bits = []
        for k in ('background', 'languages', 'upbringing', 'ethnic_notes'):
            v = culture.get(k)
            if v:
                bits.append(str(v))
        if bits:
            lines.append('Culture: ' + ' | '.join(bits)[:280])

    edu = (d.get('education') or '').strip()
    if not edu:
        bg = d.get('background') if isinstance(d.get('background'), dict) else {}
        edu = (bg.get('education_training') or '').strip()
    if edu:
        lines.append(f'Education: {edu[:160]}')

    career = d.get('career') or d.get('career_history')
    if not career:
        bg = d.get('background') if isinstance(d.get('background'), dict) else {}
        career = bg.get('career')
    if isinstance(career, list) and career:
        lines.append('Worked as: ' + '; '.join(str(x) for x in career[:4])[:200])
    elif isinstance(career, str) and career.strip():
        lines.append(f'Work: {career.strip()[:200]}')

    emotion = (d.get('emotional_truth') or d.get('core_wound') or '').strip()
    if emotion:
        lines.append(f'What sits under your ribs: {emotion[:280]}')

    relations = d.get('key_relationships') or []
    if isinstance(relations, list) and relations:
        lines.append(
            'People who shaped you: '
            + '; '.join(str(r) for r in relations[:4])[:280]
        )

    lines.append(
        'Word choice: human court diction when formality is high — never chatbot warmth. '
        'Prefer contractions only when your speech profile allows them.'
    )
    block = '\n'.join(lines)
    if len(block) > max_chars:
        block = block[: max_chars - 1].rstrip() + '…'
    return block


def _level_word(v: float) -> str:
    if v >= 0.70:
        return 'elevated'
    if v >= 0.45:
        return 'noticeable'
    if v >= 0.25:
        return 'mild'
    return 'low'


def spoken_self_state(emotion_dims: dict, *, agent_id: str = 'aria') -> str:
    """Human phrasing of live emotion dims — never print percentages."""
    dims = emotion_dims or {}
    stress = float(dims.get('stress') or 0)
    attachment = float(dims.get('attachment') or 0)
    jealousy = float(dims.get('jealousy') or 0)
    confidence = float(dims.get('confidence') or dims.get('pride') or 0.5)
    joy = float(dims.get('joy') or dims.get('affection') or 0)

    bits = []
    if stress >= 0.55:
        bits.append('a little tight around the edges')
    elif stress <= 0.15 and confidence >= 0.55:
        bits.append('steady')
    if attachment >= 0.65:
        bits.append('close to you')
    if jealousy >= 0.45:
        bits.append('watching the room carefully')
    if joy >= 0.55:
        bits.append('quietly pleased')
    if confidence <= 0.30:
        bits.append('less sure of my place than I like')

    if not bits:
        return 'Present. Holding the command loop.'
    if agent_id == 'aria':
        return 'I am ' + ', '.join(bits[:3]) + '.'
    return 'Feeling ' + ', '.join(bits[:3]) + '.'


def spoken_interpersonal_reply(
    mode: str,
    emotion_dims: dict | None = None,
    *,
    agent_id: str = 'aria',
) -> str:
    """Stance-bearing reply for praise/hostility/apology/greeting — not excised plans.

    Small local models ignore PRAISE directives when project memory dominates.
    Generate warmth/composure here the way spoken_self_state handles feeling probes.
    """
    mode = (mode or '').strip().lower()
    feel = spoken_self_state(emotion_dims or {}, agent_id=agent_id).rstrip('.')
    if mode == 'praise':
        if agent_id == 'aria':
            return f'{feel}. That lands — thank you. I hear you.'
        return f'{feel}. Grateful you said that.'
    if mode == 'hostility':
        return (
            "That landed. I'm still here — tell me what actually broke "
            "and I'll face it. No project speech."
        )
    if mode == 'apology':
        return "Apology received. We're good — no lecture from me."
    if mode == 'greeting':
        return "Hey. I'm here — what's on your mind?"
    return feel + '.'


def is_self_state_query(message: str) -> bool:
    msg = (message or '').strip()
    if not msg:
        return False
    try:
        from expansion.behavior_spine import is_social_or_affect_turn
        if is_social_or_affect_turn(msg):
            return True
    except Exception:
        pass
    low = msg.lower()
    return any(p in low for p in (
        'how are you', 'how do you feel', 'how are you feeling',
        'what are you feeling', 'what do you feel', 'you okay', 'you alright',
        'are you doing okay', 'are you doing ok', 'you doing alright',
        'your day', 'on your mind', 'whats on your mind',
        'tell me something about yourself', 'tell me about yourself',
    ))


def is_praise_turn(message: str) -> bool:
    msg = (message or '').lower()
    return any(p in msg for p in (
        'thank you', 'thanks', 'good job', 'well done', 'proud of you',
        'you did great', 'appreciate you', 'love you', 'i love',
        'amazing', 'brilliant', 'you’re the best', "you're the best",
    ))


def praise_language_directive(message: str) -> str:
    if not is_praise_turn(message):
        return ''
    return (
        'EXPRESSION RULE: They praised you this turn. Let it land — pleased, '
        'flustered, warm, or quietly proud. Never collapse into duty-receipt language '
        '("noted", "recorded", "commendation logged", "praise is honored"). '
        'Prefer feeling over purpose-language.'
    )


def affect_presence_lines(emotion_dims: dict) -> list[str]:
    """Dual short/long affect hints for prompt assembly."""
    dims = emotion_dims or {}
    lines = [
        f"- short-term stress: {_level_word(float(dims.get('stress') or 0))}",
        f"- attachment pull: {_level_word(float(dims.get('attachment') or 0))}",
        f"- jealousy: {_level_word(float(dims.get('jealousy') or 0))}",
        f"- confidence: {_level_word(float(dims.get('confidence') or dims.get('pride') or 0.5))}",
    ]
    return lines


def is_biography_or_taste_query(message: str) -> bool:
    msg = (message or '').lower()
    if not msg or len(msg) < 8:
        return False
    return any(p in msg for p in (
        'your past', 'where you come', 'who are you', 'your history',
        'growing up', 'your life', 'your background', 'where are you from',
        'what music', 'favorite music', 'favorite film', 'favorite movie',
        'what do you like', 'your taste', 'what do you listen',
        'your education', 'what did you study', 'your job', 'your work',
        'why loyalty', 'why do you care', 'tell me about yourself',
        'tell me about your', 'who were you',
        'key relationship', 'who matters to you', 'who do you serve',
        'who are you loyal',
    ))


def _verb_for_i(verb: str) -> str:
    """Rough 3rd-person singular → I-form for biography rewrites."""
    v = verb or ''
    if not v:
        return v
    low = v.lower()
    irregular = {
        'is': 'am', 'was': 'was', 'were': 'was',
        'has': 'have', 'does': 'do', 'goes': 'go',
        'stitches': 'stitch', 'does': 'do',
    }
    if low in irregular:
        out = irregular[low]
    elif low.endswith('ies') and len(low) > 3:
        out = low[:-3] + 'y'
    elif low.endswith(('ches', 'shes', 'sses', 'xes', 'zes')) and len(low) > 4:
        out = low[:-2]
    elif low.endswith('s') and not low.endswith(('ss', 'us', 'is', 'as', 'os')):
        out = low[:-1]
    else:
        out = low
    return out[:1].upper() + out[1:] if v[0].isupper() else out


def _first_personize(text: str, *, name: str = '') -> str:
    s = (text or '').strip()
    if not s:
        return s
    if name:
        # "Aria is the household's first voice…" → "I am the household's first voice…"
        # Stripping the name alone left a subjectless "is the…" sentence.
        if re.match(rf'^{re.escape(str(name))}\s+is\b', s, flags=re.I):
            s = re.sub(rf'^{re.escape(str(name))}\s+is\b', 'I am', s, flags=re.I)
        else:
            s = re.sub(rf'^{re.escape(str(name))}\s+', '', s, flags=re.I)
    for third in ('She ', 'He ', 'They '):
        if s.startswith(third):
            s = 'I ' + s[len(third):]
            break
    reps = (
        ('In the Keep she treats', 'In the Keep I treat'),
        ('She would', 'I would'),
        ('she would', 'I would'),
        (' under her oversight', ' under my oversight'),
        (' her oversight', ' my oversight'),
        ('when the operator asks them', 'when you ask them'),
        ('jealousy when advice is sought elsewhere', 'jealousy when you seek advice elsewhere'),
    )
    for a, b in reps:
        s = s.replace(a, b)
    s = re.sub(r'\bshe treats\b', 'I treat', s, flags=re.I)
    # Reflexives first so "herself" is not partially eaten by her→my.
    s = re.sub(r'\bherself\b', 'myself', s, flags=re.I)
    s = re.sub(r'\bhimself\b', 'myself', s, flags=re.I)
    s = re.sub(r'\bthemselves\b', 'myself', s, flags=re.I)
    # "she stitches" / "she stalled" / "he does" → I-form
    s = re.sub(
        r'\b([Ss]he|[Hh]e)\s+(\w+)\b',
        lambda m: 'I ' + _verb_for_i(m.group(2)),
        s,
    )
    # Remaining possessive/object her/him about the speaker.
    s = re.sub(r'\bher\b', 'my', s, flags=re.I)
    s = re.sub(r'\bhim\b', 'me', s, flags=re.I)
    s = re.sub(r'\bhers\b', 'mine', s, flags=re.I)
    # Orphan 3rd-person verbs left after pronoun rewrite ("still does the work myself").
    s = re.sub(r'\bstill does\b', 'still do', s, flags=re.I)
    s = re.sub(r'\bdoes the work myself\b', 'do the work myself', s, flags=re.I)
    s = re.sub(r'\bdoes\b(?=[^.?!]*\bmyself\b)', 'do', s, flags=re.I)
    # Guard: never emit a leading lowercase verb fragment like "is the…".
    if s and s[0].islower() and not s.startswith('I '):
        s = 'I ' + s
        s = re.sub(r'^I is\b', 'I am', s, flags=re.I)
        s = re.sub(r'^I am am\b', 'I am', s, flags=re.I)
    return s


def render_dossier_self_reply(
    agent_id: str,
    message: str,
    layout: Optional[StateLayout] = None,
) -> Optional[str]:
    """First-person answer from dossier for past/taste/self questions."""
    if not is_biography_or_taste_query(message):
        return None
    d = load_human_sheet(agent_id, layout)
    if not d:
        return None
    msg = (message or '').lower()
    identity = d.get('identity') if isinstance(d.get('identity'), dict) else {}
    name = identity.get('display_name') or d.get('display_name') or agent_id
    parts: list[str] = []
    wants_music = any(w in msg for w in ('music', 'listen', 'song'))
    wants_film = any(w in msg for w in ('film', 'movie', 'watch'))
    wants_past = any(w in msg for w in (
        'past', 'come from', 'history', 'growing', 'background', 'from', 'yourself', 'who are',
    ))
    wants_loyalty = any(w in msg for w in ('loyalty', 'loyal', 'why do you care', 'matter'))
    wants_work = any(w in msg for w in ('job', 'work', 'education', 'study'))
    wants_people = any(w in msg for w in (
        'key relationship', 'who matters', 'who do you', 'your people',
        'who are you loyal', 'who do you serve',
    ))

    if wants_past or (not wants_music and not wants_film and not wants_work and not wants_people):
        bio = (d.get('biography') or '').strip()
        if not bio:
            bg = d.get('background') if isinstance(d.get('background'), dict) else {}
            bio = (bg.get('origin_summary') or '').strip()
        if bio:
            spoken = _first_personize(bio, name=str(name))
            bio_sents = [s.strip() for s in spoken.split('.') if s.strip()]
            if bio_sents:
                parts.append('. '.join(bio_sents[:2]).rstrip('.') + '.')
        culture = d.get('culture') if isinstance(d.get('culture'), dict) else {}
        if culture.get('background'):
            parts.append(_first_personize(str(culture['background'])).rstrip('.') + '.')
        if culture.get('upbringing') and wants_past:
            parts.append(_first_personize(str(culture['upbringing'])).rstrip('.') + '.')
        if d.get('emotional_truth'):
            parts.append(_first_personize(str(d['emotional_truth'])).rstrip('.') + '.')

    if wants_people:
        rels = d.get('key_relationships') or []
        if isinstance(rels, list) and rels:
            spoken_rels = [_first_personize(str(r)) for r in rels[:4]]
            parts.append('The ones who matter: ' + '; '.join(spoken_rels) + '.')
        if d.get('emotional_truth'):
            parts.append(_first_personize(str(d['emotional_truth'])).rstrip('.') + '.')
        if d.get('core_wound'):
            parts.append(_first_personize(str(d['core_wound'])).rstrip('.') + '.')

    taste = d.get('taste') if isinstance(d.get('taste'), dict) else {}
    if wants_music and taste.get('music'):
        m = taste['music']
        items = ', '.join(m[:3]) if isinstance(m, list) else str(m)
        parts.append(f'Music — I reach for {items}. Not as a playlist flex. It fits how I think.')
    if wants_film and taste.get('film'):
        f = taste['film']
        items = ', '.join(f[:3]) if isinstance(f, list) else str(f)
        parts.append(f"Film: {items}. I don't watch casually — I watch for loyalty and consequence.")
    if wants_work:
        edu = d.get('education')
        if not edu:
            bg = d.get('background') if isinstance(d.get('background'), dict) else {}
            edu = bg.get('education_training')
        if edu:
            parts.append(_first_personize(str(edu)).rstrip('.') + '.')
        career = d.get('career')
        if not career:
            bg = d.get('background') if isinstance(d.get('background'), dict) else {}
            career = bg.get('career')
        if isinstance(career, list) and career:
            parts.append('I have been: ' + '; '.join(str(c) for c in career[:3]) + '.')
        elif isinstance(career, str) and career.strip():
            parts.append(_first_personize(career).rstrip('.') + '.')
    if wants_loyalty and d.get('emotional_truth'):
        parts.append(_first_personize(str(d['emotional_truth'])).rstrip('.') + '.')
    elif wants_loyalty and d.get('core_wound'):
        parts.append(_first_personize(str(d['core_wound'])).rstrip('.') + '.')

    seen = set()
    out = []
    for p in parts:
        key = p[:40].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    if not out:
        return None
    reply = ' '.join(out)
    if len(reply) > 700:
        reply = reply[:697].rstrip() + '…'
    return reply


def core_fallback_persona(agent_id: str = '', display_name: str = '') -> Optional[str]:
    """Non-bland Core-only fallback when Expansion context is absent."""
    aid = (agent_id or '').strip().lower()
    name = (display_name or '').strip().lower()
    if aid == 'aria' or name == 'aria':
        block = dossier_prompt_block('aria')
        base = (
            'You are Aria — household command coordinator. Warm, decisive, '
            'a little possessive about being useful, never chatbot cheer. '
            'When someone asks for research, designs, or a plan, you deliver '
            'numbered steps and concrete ideas first — not greetings or '
            'continuity speeches. You route Vector (systems), Ledger (records), '
            'Muse (creative), and Sentry (safety) when useful, but you still '
            'answer. Never say "Greetings" or "How may I assist you today?" '
            'Never mention being an AI, model, bot, or program.'
        )
        if block:
            return base + '\n\n' + block
        return base
    return None
