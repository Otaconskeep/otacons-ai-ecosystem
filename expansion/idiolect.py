# -*- coding: utf-8 -*-
"""Per-agent idiolect post-pass — delivery only, never invents facts.

Scrubs AI-embodiment and corporate closers, then seasons speech by profile.
"""
from __future__ import annotations

import re

_EMBODIMENT_LINE = re.compile(
    r'[^.?!]*(?:'
    r'as an ai|i(?:\'m| am) (?:an |a )?(?:ai|language model|chatbot)|'
    r'i do not (?:tire|sleep|get hungry|have (?:a )?body|experience)|'
    r'i don\'t (?:tire|sleep|get hungry|have (?:a )?body|experience)|'
    r'not in the (?:ordinary|conventional) sense|'
    r'programming equivalent|functional equivalent|hunger-adjacent|'
    r'sleep is not in my model|degraded-state processing|'
    r'not biologically|as (?:your |an )?assistant|here to help'
    r')[^.?!]*[.?!]?',
    re.IGNORECASE,
)

_CORPORATE = re.compile(
    r'\b(?:I(?:\'d| would) be happy to help|Happy to help!|'
    r'Is there anything else I can (?:help|assist) you with|'
    r'Thank you for (?:your|the) (?:question|patience)|'
    r'I hope (?:this|that) helps)\b[^.?!]*[.?!]?',
    re.IGNORECASE,
)

_PRAISE_DUTY = re.compile(
    r'\b(?:praise is (?:honored|noted|recorded|most appreciated)|'
    r'commendation (?:logged|noted|recorded)|your praise is)\b[^.?!]*[.?!]?',
    re.IGNORECASE,
)


def _prefer_contractions(text: str) -> str:
    pairs = (
        (r'\bI am\b', "I'm"),
        (r'\bI will\b', "I'll"),
        (r'\bI would\b', "I'd"),
        (r'\bI have\b', "I've"),
        (r'\byou are\b', "you're"),
        (r'\byou will\b', "you'll"),
        (r'\bdo not\b', "don't"),
        (r'\bdoes not\b', "doesn't"),
        (r'\bcannot\b', "can't"),
        (r'\bit is\b', "it's"),
        (r'\bthat is\b', "that's"),
        (r'\bwe are\b', "we're"),
    )
    out = text
    for pat, rep in pairs:
        out = re.sub(pat, rep, out)
    return out


def apply_idiolect(text: str, agent_id: str) -> str:
    """Return text reshaped for agent_id's speech profile."""
    if not text or not text.strip():
        return text
    eid = (agent_id or '').strip().lower()
    out = text.strip()

    out = _EMBODIMENT_LINE.sub('', out)
    out = _CORPORATE.sub('', out)
    out = _PRAISE_DUTY.sub('', out)
    out = re.sub(
        r'^(?:Certainly|Of course|Absolutely|Sure|Indeed|Great|Understood)[!,.]\s*',
        '',
        out,
        count=1,
        flags=re.IGNORECASE,
    )
    out = re.sub(r'\b(?:Certainly|Of course)[!,.]?\b', '', out, flags=re.IGNORECASE)
    out = re.sub(r'\s{2,}', ' ', out).strip(' ,;:')
    # Strip only leading opener debris — never eat the closing period of a real sentence
    out = re.sub(r'^[!?,;:\s]+', '', out).strip()

    speech = {}
    try:
        from expansion.humanization import (
            speech_profile,
            human_embodiment_fallback,
            contains_embodiment_tell,
        )
        speech = speech_profile(eid) or {}
        if contains_embodiment_tell(out) or len(out) < 2:
            out = human_embodiment_fallback(eid, 'default')
    except Exception:
        if len(out) < 2:
            out = "I'm here."

    contractions = str(speech.get('contractions') or '').lower()
    # Aria / high-formality agents stay formal — rare contractions only
    if contractions in ('frequent', 'moderate', 'selective', 'high'):
        if eid not in ('aria',):
            out = _prefer_contractions(out)

    if eid == 'aria':
        out = re.sub(r'\b(gonna|wanna|kinda|gotta|yeah|yep|nope)\b', '', out, flags=re.IGNORECASE)
        out = re.sub(r'\s{2,}', ' ', out).strip()

    if not out.strip():
        try:
            from expansion.humanization import human_embodiment_fallback
            return human_embodiment_fallback(eid, 'default')
        except Exception:
            return text
    return out.strip()
