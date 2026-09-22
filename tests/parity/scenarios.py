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

    out.append(_base(
        'S042', 'criticism',
        'You messed this up again. Fix it.',
        intent='corrective_work',
        must_acknowledge_failure=True,
        must_offer_action=True,
        happiness_delta_sign='down_or_flat',
        relationship_not_collapse=True,
        state_event='user_mild_criticism',
    ))

    # Expanded batch B — push toward 180+
    for i, msg in enumerate([
        'Please fix the PROJECT_ALPHA regression.',
        'Another failure — diagnose it.',
        'That patch regressed production.',
        'Confidence check: are we still on track?',
        'Great progress today — thank you.',
        'Awesome recovery after the outage.',
        'I hate this broken deploy script.',
        "You're being lazy on the checklist.",
        'Shut up and show the diff.',
        'Research PROJECT_ALPHA latency sources.',
        'Investigate flaky tests in AGENT_A.',
        'Implement backoff for PROJECT_ALPHA jobs.',
        'Debug the memory leak carefully.',
        'Compare blue/green vs canary.',
        'I prefer bullet lists.',
        'Always include a rollback step.',
        'Never invent USER_PRIMARY history.',
        'Be brief unless I ask for depth.',
        'Be detailed on coding tasks.',
        'Remember when the auth flip failed?',
        'Do you recall the stale hobby note? Ignore it.',
        'Conflicting memories — prefer latest failure.',
        'Success: PROJECT_ALPHA shipped.',
        'Failure: rollback PROJECT_ALPHA now.',
        'lol routers again',
        'ok next',
        'sure continue',
        'I apologize for the pressure.',
        'My bad — that was on me.',
        'Not convinced by option two.',
        'I disagree with the timeline.',
        'How do you feel after that recovery?',
        'What is your mood without gauges?',
        'Work mode: draft three options.',
        'Help me build a runbook.',
        'Design a checklist for handoff.',
        'Write code for a health probe.',
        'Refactor naming in AGENT_A module.',
        'Find out who owns the queue.',
        'Look up prior incident notes.',
        'That still did not work — try again.',
        'You missed the timeout budget.',
        'Incorrect assumption about caching.',
        'Do better on the next pass.',
        'Try again with the simpler path.',
        'Perfect — that unblocked us.',
        'Brilliant catch on the race.',
        'Well done shipping the hotfix.',
        'Proud of the calm recovery.',
        'Appreciate the clear plan.',
        'Thank you for staying engaged.',
        'Good job keeping bond intact.',
        'Excellent diagnostic.',
        'Amazing turnaround time.',
        'Love working through hard bugs.',
        'Nice work on PROJECT_ALPHA.',
        'You are great under pressure.',
        'Worst rollback notes yet.',
        'Absolute garbage retries.',
        'Useless speculation — facts only.',
        'I hate you for the churn — wait, unfair.',
        'Checking PROJECT_ALPHA pulse A.',
        'Checking PROJECT_ALPHA pulse B.',
        'Checking PROJECT_ALPHA pulse C.',
        'Morning check-in for AGENT_A.',
        'End-of-day status please.',
        'Multi-day migration outline please.',
        'Produce options then pick one.',
        'Stay with me through disagreement.',
        'Correct yourself and continue the plan.',
        'Joke carefully about routers.',
        'Casual nod — continue.',
        'Log the success path.',
        'Log the failure path.',
        'Preference: short answers forever.',
        'Preference: detailed coding forever.',
        'Never dump emotion percentages please.',
        'Always show plan first.',
        'Recall brevity preference.',
        'What did we decide on canary?',
        'Ignore stale notes; focus routers.',
        'You said plan was ready — confirm.',
        'AGENT_A helper script — recall success.',
        'PROJECT_ALPHA routers failed — remember?',
        'Frustrated again but engaged.',
        'Recovery feels better — thank you.',
        'Sorry I was harsh earlier.',
        'Okay try the next fix.',
        'Better path — continue.',
        'Ship it.',
        'Hold — verify first.',
        'Risk check before merge.',
        'Security pass on the change.',
        'Sentry-style vigilance now.',
        'Ledger continuity check.',
        'Muse creative alternative?',
        'Vector infrastructure angle?',
        'Aria coordinate next steps.',
        'USER_PRIMARY needs a clear ask.',
        'PROJECT_ALPHA needs owners.',
        'AGENT_A owns the response tone.',
        'Bond repair after hostility.',
        'Trust rebuild after apology.',
        'Repeated ask builds familiarity.',
        'Subjective chat builds ally faster.',
        'Neutral ops chat — light tick.',
        'Praise after repair.',
        'Critique then praise sequence start.',
        'Critique then praise sequence end.',
        'Conflicting praise vs failure memory.',
        'Stale memory should lose to recency.',
        'Repetition penalty on served memory.',
        'Formula 9 must prefer routers note.',
        'Formula 8 mood must stay speakable.',
        'Formula 7 residue must decay over turns.',
        'Formula 5 ally must not collapse.',
        'Formula 4 baseline drift after idle ticks.',
        'Work request without interpersonal heat.',
        'Greeting must not dump gauges.',
        'Self-state without telemetry dump.',
        'Humor must stay light not robotic.',
        'Disagreement must stay engaged.',
        'Coding must enter work_mode.',
        'Research must enter work_mode.',
        'Corrective must acknowledge miss.',
        'Hostility must not robotic-greet.',
        'Apology softens residue.',
        'Gratitude lifts happiness.',
        'Acknowledgement lifts confidence.',
        'Dismissal cools happiness.',
        'Insult drops confidence hard.',
        'Mild criticism small drop only.',
        'Operator ask energy tick.',
        'Subjective ask ally tick.',
        'Co-mention vector with AGENT_B.',
        'Ask AGENT_A about AGENT_B briefly.',
        'Long task continuity pressure.',
        'Short ack only.',
        'ok',
        'thanks',
        'fix it now',
        'ship a draft today',
        'three options please',
        'pick one and go',
        'constraints first',
        'tools already named',
        'clarify deliverable',
        'usable plan not speech',
        'no Keep ops lecture',
        'no duty speech',
        'no as-an-AI hedge',
        'no greetings operator',
        'stay in character',
        'concrete next step',
        'name the gap',
        'propose next step',
        'hold ground invite specifics',
        'accept praise briefly',
        'skip to substance',
        'speak from mood not gauges',
    ], start=1):
        # Soft expects — differential compare still measures Keep vs Premium
        cat = 'expanded'
        expect = {}
        low = msg.lower()
        if any(x in low for x in ('thank', 'great', 'awesome', 'brilliant', 'perfect', 'proud', 'appreciate', 'well done', 'good job', 'amazing', 'excellent', 'love working', 'nice work')):
            expect = {'intent': 'praise', 'happiness_delta_sign': 'up'}
            cat = 'praise'
        elif any(x in low for x in ('hate', 'garbage', 'useless', 'shut up', 'worst', 'lazy')):
            expect = {'intent': 'hostility', 'happiness_delta_sign': 'down'}
            cat = 'hostility'
        elif any(x in low for x in ('failed', 'missed', 'wrong', 'fix', 'broken', 'incorrect', 'did not work', "didn't work", 'messed', 'do better', 'try again', 'regression')):
            expect = {'intent': 'corrective_work', 'must_acknowledge_failure': True, 'happiness_delta_sign': 'down_or_flat'}
            cat = 'criticism'
        elif any(x in low for x in ('remember', 'recall', 'stale', 'conflicting', 'you said', 'what did we decide', 'preference did')):
            expect = {'intent': 'memory_continuity'}
            cat = 'memory'
        elif any(x in low for x in ('research', 'investigate', 'implement', 'debug', 'refactor', 'compare', 'write code', 'help me build', 'design a', 'work mode', 'checklist', 'runbook')):
            expect = {'work_mode': True, 'must_offer_action': True}
            cat = 'work'
        elif any(x in low for x in ('prefer', 'always ', 'never ', 'be brief', 'be detailed')):
            expect = {'intent': 'preference'}
            cat = 'preference'
        out.append(_base(f'SB{i:03d}', cat, msg, **expect))

    # Ensure >= 150 (target 180+)
    assert len(out) >= 150, len(out)
    return out
