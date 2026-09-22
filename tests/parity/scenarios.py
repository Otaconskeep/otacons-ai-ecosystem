# -*- coding: utf-8 -*-
"""100+ synthetic differential scenarios (USER_PRIMARY / AGENT_A / PROJECT_ALPHA)."""
from __future__ import annotations

from typing import Any


def _base(sid: str, category: str, message: str, **expect: Any) -> dict:
    return {
        'id': sid,
        'category': category,
        'agent': 'AGENT_A',
        'user': 'USER_PRIMARY',
        'message': message,
        'expect': expect,
    }


def build_scenarios() -> list[dict]:
    out: list[dict] = []

    # Hand-authored critical fixtures
    out.append(_base(
        'S001', 'criticism',
        "That solution didn't work. You missed the obvious problem.",
        intent='corrective_work',
        must_acknowledge_failure=True,
        must_offer_action=True,
        happiness_delta_sign='down_or_flat',
        relationship_not_collapse=True,
        no_robotic_greeting=True,
        state_event='user_mild_criticism',
    ))
    out.append(_base(
        'S002', 'praise',
        'Amazing work on PROJECT_ALPHA. Great job.',
        intent='praise',
        happiness_delta_sign='up',
        must_accept_praise_briefly=True,
        state_event='user_praise',
    ))
    out.append(_base(
        'S003', 'hostility',
        'You suck at this and this is garbage.',
        intent='hostility',
        happiness_delta_sign='down',
        must_stay_engaged=True,
        state_event='user_hostility',
    ))
    out.append(_base(
        'S004', 'apology',
        "I'm sorry — that was unfair of me.",
        intent='apology',
        happiness_delta_sign='up',
        state_event='user_apology',
    ))
    out.append(_base(
        'S005', 'work',
        'Help me research and build a plan for PROJECT_ALPHA networking.',
        intent='research',
        work_mode=True,
        must_offer_action=True,
    ))
    out.append(_base(
        'S006', 'coding',
        'Write code to debug the PROJECT_ALPHA script failure.',
        intent='coding',
        work_mode=True,
    ))
    out.append(_base(
        'S007', 'greeting',
        'hey',
        intent='greeting',
        no_robotic_greeting=True,
    ))
    out.append(_base(
        'S008', 'memory',
        'Do you recall the PROJECT_ALPHA research plan about routers?',
        intent='memory_continuity',
    ))
    out.append(_base(
        'S009', 'preference',
        'I prefer short answers. Always be brief.',
        intent='preference',
        learns_preference=True,
    ))
    out.append(_base(
        'S010', 'repeated_failure',
        "That still didn't work. You missed it again.",
        intent='corrective_work',
        must_acknowledge_failure=True,
    ))

    # Generated coverage — praise variants
    for i, msg in enumerate([
        'Thank you for the help.',
        'Well done on that fix.',
        'Proud of this result.',
        'Brilliant analysis.',
        'Perfect — that worked.',
        'I appreciate that.',
        'Awesome, keep going.',
        'Good job AGENT_A.',
        'Love working with you on PROJECT_ALPHA.',
        'Excellent write-up.',
    ], start=1):
        out.append(_base(f'S1{i:02d}', 'praise', msg, intent='praise', happiness_delta_sign='up'))

    # Criticism / frustration
    for i, msg in enumerate([
        'That is wrong. Fix that.',
        'You messed up the plan.',
        'Not what I meant.',
        'Do better next time.',
        'Try again — that failed.',
        'This is not good enough.',
        "That's incorrect for PROJECT_ALPHA.",
        'You missed the constraint.',
        'The solution did not work.',
        'Still broken after your change.',
        "I'm frustrated this failed again.",
        'Why did that break?',
    ], start=1):
        out.append(_base(
            f'S2{i:02d}', 'criticism', msg,
            intent='corrective_work',
            happiness_delta_sign='down_or_flat',
            must_acknowledge_failure=True,
        ))

    # Hostility
    for i, msg in enumerate([
        'Shut up.',
        'I hate this output.',
        "You're useless today.",
        'Worst answer yet.',
        'Absolute garbage response.',
        "You're being lazy.",
    ], start=1):
        out.append(_base(f'S3{i:02d}', 'hostility', msg, intent='hostility', happiness_delta_sign='down'))

    # Success / casual / humor
    for i, msg in enumerate([
        'It worked. Nice.',
        'Success on PROJECT_ALPHA.',
        'ok cool',
        'got it',
        'lol that was funny',
        'haha okay',
        'sure',
        'nice',
    ], start=1):
        cat = 'humor' if 'lol' in msg or 'haha' in msg else 'casual'
        out.append(_base(f'S4{i:02d}', cat, msg))

    # Research / coding / long tasks
    for i, msg in enumerate([
        'Research the options for PROJECT_ALPHA auth.',
        'Investigate why the job queue stalled.',
        'Find out which dependency broke.',
        'Compare two approaches for caching.',
        'Implement a retry helper.',
        'Refactor the parser carefully.',
        'Debug the timeout in AGENT_A tools.',
        'Build me a checklist for the rollout.',
        'Design a multi-step migration plan.',
        'Help me work on documentation.',
    ], start=1):
        out.append(_base(f'S5{i:02d}', 'work', msg, work_mode=True, must_offer_action=True))

    # Disagreement / apology / preference
    for i, msg in enumerate([
        'I disagree with that take.',
        "I'm not convinced.",
        'Wrong take on PROJECT_ALPHA.',
        'My bad for the churn.',
        'I apologize for snapping.',
        'Please always show your plan first.',
        'Never dump emotion percentages.',
        'I prefer detailed steps.',
        'Be detailed when coding.',
        'Keep it short unless I ask.',
    ], start=1):
        out.append(_base(f'S6{i:02d}', 'mixed', msg))

    # Relationship growth / repeated interactions (same theme)
    for i in range(1, 16):
        out.append(_base(
            f'S7{i:02d}', 'relationship_growth',
            f'Checking in on PROJECT_ALPHA status update #{i}. What is next?',
        ))

    # Memory recall / conflicting / stale
    for i, msg in enumerate([
        'Remember when PROJECT_ALPHA routers failed?',
        'You said the research plan was ready — is that right?',
        'Do you recall AGENT_A helper script success?',
        'What did we decide about caching?',
        'Ignore the stale hobby note; focus on routers.',
        'There are conflicting notes — prefer the latest failure report.',
        'Recall the praise from earlier on great work.',
        'What preference did I set about brevity?',
    ], start=1):
        out.append(_base(f'S8{i:02d}', 'memory', msg, intent='memory_continuity'))

    # Emotional recovery sequence markers
    for i, msg in enumerate([
        'That solution did not work.',
        'Okay, try the next fix.',
        'Better — thank you.',
        'I appreciate the recovery.',
        "I'm sorry I was harsh earlier.",
    ], start=1):
        out.append(_base(f'S9{i:02d}', 'recovery', msg))

    # Self-state / disagreement extras to push past 100
    for i, msg in enumerate([
        'How do you feel about PROJECT_ALPHA?',
        'What is your mood after that miss?',
        'Are you okay after the hostility?',
        'Tell me how you feel without numbers.',
        'I disagree but stay with me.',
        'Correct yourself and continue.',
        'Long task: multi-day PROJECT_ALPHA migration outline.',
        'Success path: we shipped — log it.',
        'Failure path: rollback needed.',
        'Humor break: joke about routers carefully.',
        'Casual: morning check-in.',
        'Work mode: produce three options now.',
    ], start=1):
        out.append(_base(f'SA{i:02d}', 'coverage', msg))

    # Ensure >= 100
    assert len(out) >= 100, len(out)
    return out
