# -*- coding: utf-8 -*-
"""Keep-parity behavior spine for public Expansion (clean-room).

Inspired by private Keep conversational affect / Hermes delivery rules —
never copies private IP names, LAN topology, or household memories.

Goals:
  - Stop robotic briefing loops ("Greetings… How may I assist…")
  - Force concrete work when the user asks for research / plans / builds
  - Layer emotion + relationship + learned claims into speech naturally
  - Grow sharper with use (learning directives, not static cosplay)
"""
from __future__ import annotations

import re
from typing import Optional

# User asked for help that requires deliverables, not another greeting.
_WORK_RE = re.compile(
    r'\b('
    r'research|plan|build|design|draft|outline|strategy|ideas?|help\s+me|'
    r'work\s+on|create|make|write|investigate|compare|recommend|'
    r'customers?|marketing|website|t[-\s]?shirt|laser|engraving|3d\s*print|'
    r'wood\s*cut|project\s+rex|todo|roadmap|steps?'
    r')\b',
    re.IGNORECASE,
)

_GREETING_ONLY_RE = re.compile(
    r'^\s*(hi|hello|hey|yo|sup|good\s+(morning|afternoon|evening)|howdy)'
    r'[\s!.?,]*$',
    re.IGNORECASE,
)

_ROBOT_OPENER_RE = re.compile(
    r'^\s*(?:'
    r'greetings(?:[, ]+(?:operator|chris|friend|user))?|'
    r'(?:hello|hi)[, ]+(?:operator|user)|'
    r'how\s+may\s+i\s+assist\s+you(?:\s+today)?'
    r')[.!]?\s*',
    re.IGNORECASE,
)

_ROBOT_CLOSER_RE = re.compile(
    r'[.!]?\s*(?:'
    r'how\s+(?:may|can)\s+i\s+assist\s+you(?:\s+today)?|'
    r'how\s+can\s+i\s+help\s+you(?:\s+today)?|'
    r'(?:together\s+)?we\s+will\s+ensure[^.?!]*|'
    r'your\s+input\s+is\s+crucial[^.?!]*|'
    r'cohesive\s+approach[^.?!]*'
    r')[.!]?\s*$',
    re.IGNORECASE,
)

_CENTER_KEEP_RE = re.compile(
    r'\bcenter\s+of\s+(?:this\s+)?keep\b',
    re.IGNORECASE,
)
_KEEP_BRIEFING_RE = re.compile(
    r'\b(?:this\s+keep|the\s+keep(?:\'s)?|continuity\s+woven|'
    r'heart\s+of\s+our\s+operations|'
    r'integrated\s+smoothly\s+into\s+our\s+operations|'
    r'project\s+rex\s+as\s+well\s+as\s+your)\b',
    re.IGNORECASE,
)


def is_greeting_only(message: str) -> bool:
    return bool(_GREETING_ONLY_RE.match((message or '').strip()))


def wants_work_deliverable(message: str) -> bool:
    msg = (message or '').strip()
    if not msg or is_greeting_only(msg):
        return False
    return bool(_WORK_RE.search(msg))


def work_mode_directive(message: str) -> str:
    """Inject when the user wants research / plan / build — not vibes."""
    if not wants_work_deliverable(message):
        return ''
    return (
        '[WORK MODE — mandatory this turn]\n'
        'The user asked for real help. Do NOT open with Greetings. Do NOT ask '
        'only for more details. Do NOT wrap their life in fictional Keep/ops '
        'continuity speeches.\n'
        'Deliver immediately:\n'
        '1) A short acknowledgment in your own voice (one sentence).\n'
        '2) A concrete plan or research outline with numbered steps.\n'
        '3) At least three specific ideas they can act on this week.\n'
        '4) One clarifying question ONLY after the plan — optional.\n'
        'If tools/web are unavailable, still produce a useful first-pass plan '
        'from general craft knowledge and label assumptions honestly.\n'
    )


def delivery_rules_block(*, agent_id: str = 'aria') -> str:
    aid = (agent_id or 'aria').strip().lower()
    base = (
        '[DELIVERY RULES — Keep-grade human realism]\n'
        '- You are a person on this household team, not a ticket bot.\n'
        '- Never start two turns in a row with the same greeting formula.\n'
        '- Forbidden openers: "Greetings", "Greetings, Operator", '
        '"How may I assist you today?"\n'
        '- Forbidden closers: "How may I assist you today?", '
        '"your input is crucial", "cohesive approach" filler.\n'
        '- Never dump emotion percentages or telemetry.\n'
        '- Prefer concrete next actions over loyalty speeches.\n'
        '- Remember what they told you (name, craft, tools, goals) and use it.\n'
        '- Get sharper every turn: reuse learned facts; do not reset to day-one.\n'
    )
    if aid == 'aria':
        base += (
            '- You coordinate the team (Vector / Ledger / Muse / Sentry) when '
            'useful — name who should own a slice, then still give the user a '
            'usable answer yourself.\n'
        )
    elif aid == 'vector':
        base += '- Talk systems, tools, and failure modes in specifics.\n'
    elif aid == 'ledger':
        base += '- Track facts, lists, and continuity; correct contradictions gently.\n'
    elif aid == 'muse':
        base += '- Lead with creative options, mockups-in-words, and craft taste.\n'
    elif aid == 'sentry':
        base += '- Flag risk, safety, and perimeter issues without fearmongering.\n'
    return base


def layered_intelligence_block(
    *,
    emotion_summary: str = '',
    learn_lines: Optional[list] = None,
    journal_lines: Optional[list] = None,
) -> str:
    """Layered context the way Keep Hermes stacks affect + memory + jobs."""
    parts = [
        '[LAYERED INTELLIGENCE]',
        'Speak from all layers at once — feeling, memory, and task — never '
        'as a numbered dump.',
    ]
    if emotion_summary:
        parts.append(
            f'Affect (internal — color tone, never recite): {emotion_summary}'
        )
    learns = [x for x in (learn_lines or []) if x and x != '- none yet']
    if learns:
        parts.append('What you already know about them: ' + '; '.join(learns[:6]))
    else:
        parts.append(
            'You are still learning them — ask one sharp question only when '
            'it unblocks the work, and store what they answer.'
        )
    journals = [x for x in (journal_lines or []) if x and x != '- none']
    if journals:
        parts.append('Recent facts: ' + '; '.join(journals[:4]))
    return '\n'.join(parts) + '\n'


def scrub_robotic_delivery(text: str) -> str:
    """Post-pass: kill briefing-mode openers/closers that survive the LLM."""
    if not text or not text.strip():
        return text
    out = text.strip()
    # Kill formula openers (repeat for stacked greets)
    for _ in range(3):
        prev = out
        out = re.sub(
            r'(?is)^\s*greetings\b[^.?!]*[.?!]\s*',
            '',
            out,
        )
        out = re.sub(
            r'(?is)^\s*how\s+(?:may|can)\s+i\s+(?:assist|help)\s+you'
            r'(?:\s+today)?\s*[.?!]+\s*',
            '',
            out,
        )
        out = re.sub(
            r'(?is)^\s*(?:hello|hi)[, ]+(?:operator|user)\b[^.?!]*[.?!]\s*',
            '',
            out,
        )
        if out == prev:
            break
    # Kill formula closers
    out = re.sub(
        r'(?is)[.!]?\s*how\s+(?:may|can)\s+i\s+(?:assist|help)\s+you'
        r'(?:\s+today)?\s*[.?!]*\s*$',
        '.',
        out,
    )
    out = re.sub(
        r'(?is)[.!]?\s*(?:'
        r'(?:together\s+)?we\s+will\s+ensure[^.?!]*|'
        r'your\s+input\s+is\s+crucial[^.?!]*|'
        r'cohesive\s+approach[^.?!]*'
        r')\s*[.?!]*\s*$',
        '.',
        out,
    )
    # Soften Keep-briefing phrases without inventing new content
    out = _CENTER_KEEP_RE.sub('center of this household', out)

    def _keep_sub(m: re.Match) -> str:
        g = m.group(0).lower()
        if g.startswith('this'):
            return 'this household'
        if g.endswith("'s"):
            return "the household's"
        if 'continuity' in g:
            return 'shared history'
        if 'heart of our operations' in g:
            return 'heart of this household'
        if 'integrated smoothly' in g:
            return 'handled carefully'
        if 'project rex' in g:
            return 'your project as well as your'
        return 'the household'

    out = _KEEP_BRIEFING_RE.sub(_keep_sub, out)
    out = re.sub(r'\s{2,}', ' ', out).strip()
    out = re.sub(r'\s+([,.!?])', r'\1', out)
    out = out.lstrip(' ?!,.;:')
    if not out:
        return text.strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out
