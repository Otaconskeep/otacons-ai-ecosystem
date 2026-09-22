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

# Praise / hostility / apology — interpersonal; must NOT open WORK MODE.
_PRAISE_RE = re.compile(
    r'\b(?:thank(?:s| you)|good job|well done|proud of you|you did great|'
    r'appreciate (?:you|it)|i love (?:you|that)|you\'re the best|amazing|brilliant|'
    r'nice work|great work|perfect|love that|awesome|excellent|'
    r'you(?:\'re| are) (?:great|the best|helpful))\b',
    re.IGNORECASE,
)
_HOSTILE_RE = re.compile(
    r'\b(?:you(?:\'re|re| are) (?:useless|worthless|stupid|dumb|an idiot|pathetic|'
    r'ugly|hideous|gross|disgusting|fat|repulsive|lazy|garbage|a\s+bitch|a\s+cunt)|'
    r'useless|shut up|i hate you|i hate this|you suck|worst (?:agent|assistant|answer)|'
    r'dumb (?:bot|ai)|idiot|fuck you|fuck off|go to hell|asshole|piece of shit|'
    r'absolute garbage|this is garbage|being lazy|bitch|cunt|whore|bastard|'
    r'motherfucker|dumbass)\b',
    re.IGNORECASE,
)
_APOLOGY_RE = re.compile(
    r'\b(?:i(?:\'m|m| am) sorry|i apologize|forgive me|sorry (?:for|about)|'
    r'my (?:bad|apologies)|i was (?:wrong|harsh|unfair))\b',
    re.IGNORECASE,
)

# Social / affect turns — must NOT trigger WORK MODE or project restatement.
_SOCIAL_RE = re.compile(
    r'\b('
    r'how\s+do\s+you\s+feel|what\s+do\s+you\s+feel|how\s+are\s+you(?:\s+feeling)?|'
    r'how(?:\'s|\s+is|\s+was)?\s+your\s+day|talk\s+about\s+your\s+day|'
    r'how\s+are\s+you\s+doing|'
    # apostrophe-less "whats" + standard forms
    r'what(?:\'s|s|\s+is)\s+on\s+your\s+mind|'
    # optional "doing" infix: are you (doing) ok(ay)?; you (doing) alright?
    r'are\s+you(?:\s+doing)?\s+ok(?:ay)?|'
    r'(?:are\s+)?you(?:\s+doing)?\s+(?:ok(?:ay)?|alright)|'
    r'your\s+mood|emotionally|'
    r'tell\s+me\s+(?:something\s+)?about\s+yourself|'
    r'lets?\s+talk(?:\s+about)?(?!\s+the\s+(?:plan|project|fabric|shirt))|'
    r'just\s+checking\s+in|miss\s+you'
    r')\b',
    re.IGNORECASE,
)

# Day / conversation invitations — must reach the LLM, not a mood-label short-circuit.
_DAY_INVITE_RE = re.compile(
    r'\b('
    r'how(?:\'s|\s+is|\s+was)?\s+your\s+day|talk\s+about\s+your\s+day|'
    r'what(?:\'s|s|\s+is)\s+on\s+your\s+mind|'
    r'tell\s+me\s+(?:something\s+)?about\s+yourself|'
    r'lets?\s+talk(?:\s+about)?(?!\s+the\s+(?:plan|project|fabric|shirt))|'
    r'just\s+checking\s+in'
    r')\b',
    re.IGNORECASE,
)

# Narrow feeling probes — safe to answer with spoken_self_state alone.
_FEELING_ONLY_RE = re.compile(
    r'\b('
    r'how\s+do\s+you\s+feel|what\s+do\s+you\s+feel|how\s+are\s+you(?:\s+feeling)?|'
    r'how\s+are\s+you\s+doing|your\s+mood|emotionally|'
    r'are\s+you(?:\s+doing)?\s+ok(?:ay)?|'
    r'(?:are\s+)?you(?:\s+doing)?\s+(?:ok(?:ay)?|alright)'
    r')\b',
    re.IGNORECASE,
)

_EXECUTE_RE = re.compile(
    r'^\s*(?:please\s+)?(?:do\s+it|go\s+ahead|make\s+it\s+so|ship\s+it|'
    r'get\s+(?:on\s+)?with\s+it|just\s+do\s+it|execute|run\s+it)\s*[.!]?\s*$',
    re.IGNORECASE,
)

_NAME_META_RE = re.compile(
    r'(?is)(?:^|[.?!]\s*)('
    r'(?:also[, ]+)?(?:just\s+)?(?:a\s+)?(?:heads?\s*up|note|reminder)[^.?!]*?'
    r'(?:prefer\s+being\s+called|called\s+by\s+(?:their|your|an?\s+)?(?:actual\s+)?names?|'
    r'using\s+names?\s+helps|how\s+do\s+you\s+feel\s+about\s+being\s+called|'
    r'how\s+do\s+you\s+feel\s+about\s+(?:that|me\s+calling)|'
    r'being\s+called\s+by\s+your\s+name)[^.?!]*[.?!]\s*'
    r')',
)

# Invented teammate execution — strip unless board ground truth justified it.
_FAKE_TEAM_START_RE = re.compile(
    r'(?is)\b(?:vector|muse|sentry|ledger)\s+'
    r'(?:has\s+(?:already\s+)?(?:begun|started)|have\s+(?:already\s+)?(?:begun|started)|'
    r'is\s+(?:currently\s+)?(?:compiling|analyzing|researching|updating|gathering)|'
    r'will\s+(?:compile|analyze|gather|update\s+(?:the\s+)?inventory))\b[^.?!]*[.?!]\s*',
)

# Numbered / scaffolded project plans — strip on non-work interpersonal turns.
# Includes dangling lead-ins after numbered lists were excised ("three key steps").
_PLAN_SCAFFOLD_RE = re.compile(
    r'(?is)(?:'
    r'(?:let\'?s|lets)\s+get\s+back\s+(?:on\s+track|to\s+work)[^.?!]*[.?!]?\s*|'
    r'(?:let\'?s|lets)\s+(?:dive\s+in|kick\s+off|move\s+forward)[^.?!]*[.?!]?\s*|'
    r'(?:here\'?s|heres)\s+what\s+we(?:\'ll| will)\s+do\s+next\s*:?\s*|'
    r'(?:here\'?s|heres)\s+(?:a\s+)?(?:the\s+)?(?:plan|next\s+steps?)[^.?!]*[.?!]?\s*|'
    r'(?:diving?|let\'?s\s+dive)\s+into\s+(?:the\s+)?(?:next\s+steps?|shirt|project|plan)[^.?!]*[.?!]?\s*|'
    r'\b(?:back\s+to|with)\s+your\s+(?:shirt|t-?shirt|fabric)\s+project\b[^.?!]*[.?!]?\s*|'
    r'\bfor\s+(?:our|the|your)\s+(?:shirt|t-?shirt|fabric)\s+project\b[^.?!]*[.?!]?\s*|'
    r'\bwe(?:\'ll| will)\s+(?:keep\s+)?(?:this\s+)?(?:project\s+)?on\s+track[^.?!]*[.?!]?\s*|'
    r'\bwe(?:\'ll| will)\s+proceed\s+in\s+(?:\w+\s+)?(?:key\s+)?steps?\b[^.?!]*[.?!]?\s*|'
    r'\b(?:with\s+)?(?:a\s+)?(?:clear|structured)\s+plan(?:\s+right\s+away|\s+then)?\b[^.?!]*[.?!]?\s*|'
    r'\b(?:first|next)\s+up[,:]?\s+(?:let\'?s|lets)[^.?!]*[.?!]?\s*'
    r')',
)
_NUMBERED_PLAN_BLOCK_RE = re.compile(
    r'(?is)'
    # Multi-line: 1. foo\n2. bar  OR same-line: 1. **foo** 2. **bar**
    r'(?:(?:^|(?<=[.!?]))\s*)?'
    r'(?:\d+[\.)]\s*\*{0,2}[^\n\d]{3,}?\*{0,2})'
    r'(?:(?:\n+\s*|\s+)\d+[\.)]\s*\*{0,2}[^\n\d]{3,}?\*{0,2}){1,}'
)
_PHASE_PLAN_RE = re.compile(
    r'(?is)\b(?:'
    r'research\s+phase|inventory\s+update|review\s*(?:&|and)\s*selection'
    r')\s*:?[^\n]*',
)

_GREETING_ONLY_RE = re.compile(
    r'^\s*(hi|hello|hey|yo|sup|howdy|good\s+(morning|afternoon|evening))'
    r'(?:[, ]+(?:chris|josh|friend|there|everyone))?'
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


def is_praise_turn(message: str) -> bool:
    return bool(_PRAISE_RE.search((message or '').strip()))


def is_hostile_turn(message: str) -> bool:
    return bool(_HOSTILE_RE.search((message or '').strip()))


def is_apology_turn(message: str) -> bool:
    return bool(_APOLOGY_RE.search((message or '').strip()))


def is_social_or_affect_turn(message: str) -> bool:
    """True when the user wants feelings / day / check-in — not project status."""
    msg = (message or '').strip()
    if not msg:
        return False
    return bool(_SOCIAL_RE.search(msg))


def is_day_or_conversation_invite(message: str) -> bool:
    """True for day/check-in invitations that need a real conversational reply."""
    msg = (message or '').strip()
    if not msg:
        return False
    return bool(_DAY_INVITE_RE.search(msg))


def is_feeling_query_only(message: str) -> bool:
    """Narrow 'how do you feel / are you okay' — may use spoken_self_state short-circuit.

    Day invitations and "tell me about yourself" return False so the LLM path runs.
    """
    msg = (message or '').strip()
    if not msg:
        return False
    if is_day_or_conversation_invite(msg):
        return False
    return bool(_FEELING_ONLY_RE.search(msg))


def is_execute_imperative(message: str) -> bool:
    """Short 'do it' / 'go ahead' — execute pending work, do not restate the plan."""
    return bool(_EXECUTE_RE.match((message or '').strip()))


def is_interpersonal_turn(message: str) -> bool:
    """Praise / hostility / apology / greeting / social — never WORK MODE."""
    msg = (message or '').strip()
    if not msg:
        return False
    return (
        is_greeting_only(msg)
        or is_social_or_affect_turn(msg)
        or is_praise_turn(msg)
        or is_hostile_turn(msg)
        or is_apology_turn(msg)
    )


def classify_delivery_mode(message: str) -> str:
    """Single routing key for prompt directives: greeting|social|praise|hostility|apology|execute|work|chat."""
    msg = (message or '').strip()
    if not msg:
        return 'chat'
    if is_greeting_only(msg):
        return 'greeting'
    if is_social_or_affect_turn(msg):
        return 'social'
    # Interpersonal before work-keyword collisions ("great work on the plan")
    if is_hostile_turn(msg):
        return 'hostility'
    if is_praise_turn(msg):
        return 'praise'
    if is_apology_turn(msg):
        return 'apology'
    if is_execute_imperative(msg):
        return 'execute'
    if bool(_WORK_RE.search(msg)):
        return 'work'
    return 'chat'


def wants_work_deliverable(message: str) -> bool:
    msg = (message or '').strip()
    if not msg:
        return False
    mode = classify_delivery_mode(msg)
    if mode in ('greeting', 'social', 'praise', 'hostility', 'apology'):
        return False
    if mode == 'execute':
        return True
    return mode == 'work'


_NO_PROJECT_LINES = (
    '- Do NOT restate fabric, t-shirt, inventory, Ledger/Vector/Sentry plans.\n'
    '- Do NOT invent status updates ("Ledger has already begun…", '
    '"Vector will compile…"). Only cite open REX board jobs if present.\n'
    '- Do NOT ask whether you may use their name or lecture about names.\n'
)


def work_mode_directive(message: str) -> str:
    """Inject delivery mode — interpersonal beats work keywords every time."""
    msg = (message or '').strip()
    mode = classify_delivery_mode(msg)
    if mode == 'greeting':
        return (
            '[GREETING — mandatory this turn]\n'
            'Brief human hello in your own voice. Do NOT dump a project plan.\n'
            + _NO_PROJECT_LINES
            + '- One short greeting; optional one question about them.\n'
        )
    if mode == 'social':
        invite = is_day_or_conversation_invite(msg)
        return (
            '[SOCIAL / AFFECT TURN — mandatory this turn]\n'
            'The user asked about YOU (feelings, your day, check-in) — not the open project.\n'
            + (
                '- They invited conversation (day / mind / about you) — answer with a lived '
                'beat in your own voice, then ask them one question back. Do NOT reply with '
                'only a fixed mood label like "I am quietly pleased."\n'
                if invite else
                '- Answer in your own voice about how you feel.\n'
            )
            + _NO_PROJECT_LINES
            + '- Keep it short: one honest feeling beat, optional one question about them.\n'
        )
    if mode == 'praise':
        return (
            '[PRAISE — mandatory this turn]\n'
            'They praised you. Let it land — warm, brief, in character.\n'
            '- Accept the compliment; do NOT collapse into duty-receipt language.\n'
            '- Do NOT pivot to a numbered project plan or restate open work.\n'
            + _NO_PROJECT_LINES
            + '- One feeling beat; optional one light follow-up. No WORK MODE.\n'
        )
    if mode == 'hostility':
        return (
            '[HOSTILITY — mandatory this turn]\n'
            'That landed. Stay composed and engaged — not a ticket bot.\n'
            '- Acknowledge the hit without collapsing into apology loops.\n'
            '- Ask for the specific failure if unclear. Do NOT restate a fabric plan.\n'
            + _NO_PROJECT_LINES
        )
    if mode == 'apology':
        return (
            '[APOLOGY — mandatory this turn]\n'
            'They apologized. Soften briefly; do not lecture. No project restatement.\n'
            + _NO_PROJECT_LINES
        )
    if mode == 'execute':
        return (
            '[EXECUTE — mandatory this turn]\n'
            'The user said to DO the pending work — not to restate the plan.\n'
            '- One short ack that you are queueing/starting it on the REX board.\n'
            '- Name the owner (e.g. Ledger for research) and the job in one line.\n'
            '- Do NOT repeat a numbered plan. Do NOT ask fabric preference questions.\n'
            '- Do NOT ask about calling them by name.\n'
            '- Do NOT invent Vector/Muse/Sentry work that is not on the board.\n'
        )
    if mode != 'work':
        return ''
    return (
        '[WORK MODE — mandatory this turn]\n'
        'The user asked for real help. Do NOT open with Greetings. Do NOT ask '
        'only for more details. Do NOT wrap their life in fictional Keep/ops '
        'continuity speeches.\n'
        'Do NOT lecture about using names or ask how they feel about being called '
        'by their name — that is already settled; just use the name you know.\n'
        'Do NOT claim Vector/Muse/Sentry/Ledger has started work unless that agent '
        'appears under Active jobs on the REX board this turn.\n'
        'Deliver immediately:\n'
        '1) A short acknowledgment in your own voice (one sentence).\n'
        '2) A concrete plan or research outline with numbered steps.\n'
        '3) At least three specific ideas they can act on this week.\n'
        '4) One clarifying question ONLY after the plan — optional, and never '
        'about naming etiquette.\n'
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
        '- Remember what they told you (name, craft, tools, goals) and use it '
        'quietly — never ask permission to use their name, never lecture that '
        '"some users prefer actual names", never ask how they feel about being called Chris.\n'
        '- When they change topic to feelings/day/check-in/praise/insult/greeting, '
        'follow THAT topic; do not drag an unfinished project plan back into the reply.\n'
        '- Never claim Vector/Muse/Sentry/Ledger has begun or is compiling work '
        'unless that agent appears under Active jobs this turn. Prefer queueing '
        'real REX board work over inventing teammate status.\n'
        '- Get sharper every turn: reuse learned facts; do not reset to day-one.\n'
    )
    if aid == 'aria':
        base += (
            '- You coordinate the team (Vector / Ledger / Muse / Sentry) when '
            'useful — name who should own a slice, then still give the user a '
            'usable answer yourself. Do not claim a teammate "has already begun" '
            'unless a real REX board job exists for that agent.\n'
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


def scrub_plan_restatement(text: str, *, delivery_mode: str = '') -> str:
    """Strip numbered project plans from interpersonal replies (post-LLM).

    Prompt-only rules lose on small models when memory is full of the open
    project. Same pattern as fake-teammate scrub: deterministic after generate.
    """
    mode = (delivery_mode or '').strip().lower()
    if mode in ('work', 'execute'):
        return text
    if mode not in ('greeting', 'social', 'praise', 'hostility', 'apology', 'chat'):
        return text
    if not text or not text.strip():
        return text
    out = text.strip()
    out = _PLAN_SCAFFOLD_RE.sub(' ', out)
    out = _PHASE_PLAN_RE.sub(' ', out)
    # Shirt/fabric plan bullets that survived without numbers
    out = re.sub(
        r'(?is)\b(?:ledger|vector|sentry|muse)\s+will\s+'
        r'(?:start|kick\s+off|begin|ensure|adjust|update|research)[^.?!]*[.?!]\s*',
        ' ',
        out,
    )
    # Two or more numbered steps → cut from the first marker to end (same-line or multiline)
    markers = list(re.finditer(r'(?:^|[\s:])\d+[\.)]\s+\*?\*?', out, flags=re.M))
    if len(markers) >= 2:
        cut = markers[0].start()
        # Keep prior interpersonal sentence; drop the plan dump
        out = out[:cut].rstrip(' :,\n\t-')
    else:
        out = _NUMBERED_PLAN_BLOCK_RE.sub(' ', out)
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    out = re.sub(r'\s+([,.!?])', r'\1', out).strip(' ,;:')
    out = out.lstrip(' ?!,.;:')
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def scrub_robotic_delivery(
    text: str,
    *,
    user_message: str = '',
    delivery_mode: str = '',
) -> str:
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
    # Kill name-etiquette lectures / "how do you feel about being called"
    out = _NAME_META_RE.sub(' ', out)
    out = re.sub(
        r'(?is)\b(?:also[, ]+)?(?:just\s+a\s+)?(?:heads?\s*up|note|reminder)[^.?!]*?'
        r'(?:names?|being\s+called)[^.?!]*[.?!]\s*',
        '',
        out,
    )
    out = re.sub(
        r'(?is)\bhow\s+do\s+you\s+feel\s+about\s+(?:being\s+called|that|me\s+calling)[^.?!]*[.?!]\s*',
        '',
        out,
    )
    out = re.sub(
        r'(?is)\b(?:for\s+now[, ]+)?i(?:\'ll| will)\s+continue\s+using\s+\w+'
        r'[^.?!]*?(?:prefer|name)[^.?!]*[.?!]\s*',
        '',
        out,
    )
    # Kill invented teammate "already begun / is compiling" claims
    out = _FAKE_TEAM_START_RE.sub(' ', out)
    # Non-work modes: strip plan scaffolding the model ignored in the prompt
    mode = (delivery_mode or '').strip()
    if not mode and user_message:
        mode = classify_delivery_mode(user_message)
    if mode and mode not in ('work', 'execute'):
        out = scrub_plan_restatement(out, delivery_mode=mode)
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
        # Do not restore the pre-scrub text — that reintroduces name lectures /
        # invented teammate starts we just removed.
        return ''
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out
