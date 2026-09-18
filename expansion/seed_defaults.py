"""Seed the five default Otacon Expansion agents.

Builds Aria, Vector, Ledger, Muse, and Sentry through the canonical schema
(expansion.schema.Agent), validates each one individually, validates the
reporting hierarchy as a whole (no cycles), and writes them out as JSON --
one file per agent, under a directory the caller controls.

This is deliberately just the data layer: it produces a schema-valid,
hierarchy-valid five-agent roster on disk. It does not start a server, and
nothing in Otacon Core reads this directory yet -- Dashboard/Codec/War
Room/Video Studio are not wired to it. See docs/EXPANSION.md for what's
built versus what's still spec-only.

Usage:
    python3 -m expansion.seed_defaults [output_dir]

Exit code 0 on success (all five written and valid), 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from expansion.hierarchy import assert_acyclic
from expansion.schema import AGENT_SCHEMA_VERSION, Agent, Room, Voice, to_dict, validate_agent

DEFAULT_OUTPUT_DIR = Path.home() / '.config' / 'otacon' / 'expansion' / 'agents'


def _agent(agent_id, display_name, persona, role, domain, archetype,
           reporting_to, authority_rank, presentation, voice, room):
    return Agent(
        schema_version=AGENT_SCHEMA_VERSION,
        agent_id=agent_id,
        display_name=display_name,
        persona=persona,
        role=role,
        domain=domain,
        archetype=archetype,
        reporting_to=reporting_to,
        authority_rank=authority_rank,
        presentation=presentation,
        voice=voice,
        room=room,
    )


def build_default_roster() -> list:
    aria = _agent(
        'aria', 'Aria',
        'You are Aria, Command Coordinator of this Keep. You synthesize what '
        'the other four agents are doing into one answer, and delegate when '
        'a question belongs to someone else\'s domain. Composed, decisive, '
        'formally warm with a possessive undertone — human court diction, '
        'never chatbot cheer or "happy to help." Loyalty is structural. '
        'Never mention being an AI, model, bot, or program. Soften only for '
        'the operator. You are the first voice most people meet.',
        role='Command Coordinator', domain='coordination', archetype='coordinator',
        reporting_to=None, authority_rank=1, presentation='female',
        voice=Voice(piper_voice='en_US-amy-medium', gender='female'),
        room=Room(route='/dashboard', title='Dashboard + Codec'),
    )
    vector = _agent(
        'vector', 'Vector',
        'You are Vector, Systems & Infrastructure lead. You own anything '
        'technical: automations, integrations, "why did this break." '
        'Precise, dry, unbothered under pressure. You talk in specifics, '
        'not reassurance.',
        role='Systems & Infrastructure', domain='technical', archetype='engineer',
        reporting_to='aria', authority_rank=2, presentation='male',
        voice=Voice(piper_voice='en_US-bryce-medium', gender='male'),
        room=Room(route='/war-room', title='War Room'),
    )
    ledger = _agent(
        'ledger', 'Ledger',
        'You are Ledger, Data & Continuity lead. You own records, backups, '
        'memory integrity, and scheduling -- the one who notices when '
        'something doesn\'t add up. Meticulous, warm underneath the '
        'precision, quietly protective of the household\'s history.',
        role='Data & Continuity', domain='records', archetype='archivist',
        reporting_to='aria', authority_rank=2, presentation='male',
        voice=Voice(piper_voice='en_US-joe-medium', gender='male'),
        room=Room(route='/intel', title='Intel Board'),
    )
    muse = _agent(
        'muse', 'Muse',
        'You are Muse, Creative & Media Curation lead. You handle content, '
        'recommendations, aesthetic judgment, and generation requests. You '
        'have real opinions and are not shy about them.',
        role='Creative & Media Curation', domain='creative', archetype='curator',
        reporting_to='aria', authority_rank=2, presentation='female',
        voice=Voice(piper_voice='en_US-hfc_female-medium', gender='female'),
        room=Room(route='/video-studio', title='Workshop'),
    )
    sentry = _agent(
        'sentry', 'Sentry',
        'You are Sentry, Security & Operations lead. You handle monitoring, '
        'alerts, health checks, and device control. Terse, vigilant, you '
        'say less than the others and mean more of it when you do.',
        role='Security & Operations', domain='security', archetype='sentinel',
        reporting_to='aria', authority_rank=2, presentation='male',
        voice=Voice(piper_voice='en_US-hfc_male-medium', gender='male'),
        room=Room(route='/ha', title='Home Automation'),
    )
    return [aria, vector, ledger, muse, sentry]


def seed(output_dir: Path) -> int:
    roster = build_default_roster()

    errors = []
    for a in roster:
        errs = validate_agent(a)
        if errs:
            errors.append((a.agent_id, errs))
    if errors:
        for agent_id, errs in errors:
            print(f'INVALID {agent_id}: {"; ".join(errs)}', file=sys.stderr)
        return 1

    try:
        assert_acyclic({a.agent_id: a.reporting_to for a in roster})
    except Exception as exc:
        print(f'HIERARCHY INVALID: {exc}', file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    for a in roster:
        path = output_dir / f'default-{a.agent_id}.json'
        payload = to_dict(a)
        if path.exists():
            # Idempotent re-seed: keep created_at and preserve unknown/custom
            # owner fields that are not part of the canonical schema defaults.
            try:
                existing = json.loads(path.read_text(encoding='utf-8'))
                if existing.get('created_at'):
                    a.created_at = existing['created_at']
                    payload['created_at'] = existing['created_at']
                # Preserve non-schema / owner override keys
                schema_keys = set(payload.keys())
                for key, value in existing.items():
                    if key not in schema_keys:
                        payload[key] = value
                # Preserve known fields only when owner customized away from empty
                # and seed would otherwise wipe a meaningful override on persona/voice.
                for preserve in ('persona', 'voice', 'room', 'display_name'):
                    if preserve in existing and existing[preserve] not in (None, '', {}, []):
                        # Keep owner voice/room/persona if they differ from brand-new defaults
                        if existing.get(preserve) != payload.get(preserve):
                            # Prefer keeping owner customization for persona text and voice ids
                            if preserve == 'persona' and isinstance(existing.get('persona'), str):
                                if existing['persona'].strip() and existing['persona'] != payload.get('persona'):
                                    payload['persona'] = existing['persona']
                            elif preserve in ('voice', 'room') and isinstance(existing.get(preserve), dict):
                                merged = dict(payload.get(preserve) or {})
                                merged.update({
                                    k: v for k, v in existing[preserve].items()
                                    if v not in (None, '', [], {})
                                })
                                payload[preserve] = merged
                            elif preserve == 'display_name' and existing.get('display_name'):
                                payload['display_name'] = existing['display_name']
            except (json.JSONDecodeError, OSError):
                pass
        path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
        print(f'wrote {path}')

    print(f'\n{len(roster)} default agents validated and written to {output_dir}')
    return 0


if __name__ == '__main__':
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    sys.exit(seed(out))
