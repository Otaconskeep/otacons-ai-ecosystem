"""Persist canonical dossiers into product/user layout and seed runtime state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from expansion.canonical_dossiers import get_canonical_dossier
from expansion.dossier import validate_canonical_dossier
from expansion.emotion_store import EmotionStore
from expansion.events import EventBus, new_event
from expansion.living_dossier_init import init_empty_living_dossier
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.motion_defaults import DEFAULT_MOTION, validated_default_manifests
from expansion.relationship_store import RelationshipStore
from expansion.schema import Agent, MotionManifestRef
from expansion.seed_defaults import build_default_roster
from expansion.state_layout import StateLayout, resolve_layout


def write_canonical_dossiers(layout: Optional[StateLayout] = None) -> list[Path]:
    """Validate that product dossier JSON exists — do not regenerate from Python.

    Canonical source of truth is expansion/product/dossiers/*.json (under the
    resolved product_root). Bootstrap/provision only confirms they load cleanly.
    """
    from expansion.canonical_dossiers import (
        clear_dossier_cache,
        get_canonical_dossier,
        list_product_dossier_paths,
    )
    layout = layout or resolve_layout()
    clear_dossier_cache()
    paths = list_product_dossier_paths(layout)
    for path in paths:
        agent_id = path.stem
        dossier = get_canonical_dossier(agent_id, layout)
        errors = validate_canonical_dossier(dossier)
        if errors:
            raise ValueError(f'{agent_id}: {errors}')
    return paths


def enrich_agent_with_p1(agent: Agent) -> Agent:
    """Attach motion manifest refs and dossier-informed emotional defaults."""
    dossier = get_canonical_dossier(agent.agent_id)
    ref = DEFAULT_MOTION.get(agent.agent_id)
    if ref:
        agent.motion_manifest = MotionManifestRef(
            manifest_id=ref.manifest_id,
            capability_level=ref.capability_level,
        )
    agent.emotional_defaults = dict(dossier.stress.emotional_baseline)
    agent.relationship_defaults = {
        'jealousy_sensitivity': dossier.social.jealousy_sensitivity,
        'possessiveness': dossier.social.possessiveness,
        'attachment_style': dossier.social.attachment_style,
    }
    # Prefer dossier persona flavor without discarding seed persona — append archetype line
    if dossier.character.archetype and dossier.character.archetype not in agent.persona:
        agent.persona = (
            f'{agent.persona} Archetype: {dossier.character.archetype}. '
            f'{dossier.character.communication_style}'
        )
    return agent


def bootstrap_runtime_state(layout: Optional[StateLayout] = None) -> dict:
    """Initialize emotion, relationships, living dossiers, journals for all five."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    write_canonical_dossiers(layout)
    validated_default_manifests()

    roster = [enrich_agent_with_p1(a) for a in build_default_roster()]
    agent_ids = [a.agent_id for a in roster]

    emotions = EmotionStore(layout)
    relationships = RelationshipStore(layout)
    memory = ExpansionMemory(layout)
    bus = EventBus(layout=layout, persist=True)

    for agent in roster:
        dossier = get_canonical_dossier(agent.agent_id)
        emotions.get_or_create(
            agent.agent_id,
            baseline=dossier.stress.emotional_baseline,
            sensitivity=_sensitivity_for(agent.agent_id, dossier),
        )
        init_empty_living_dossier(layout, agent.agent_id)
        # Journal scaffold (objective) — empty JSONL
        jpath = layout.user_journals / f'{agent.agent_id}.jsonl'
        if not jpath.exists():
            jpath.write_text('', encoding='utf-8')
        dpath = layout.user_diaries / f'{agent.agent_id}.jsonl'
        if not dpath.exists():
            dpath.write_text('', encoding='utf-8')
        # Seed one semantic self-knowledge memory (canonical, not owner history)
        existing = memory.list(agent.agent_id)
        if not any(m.kind == 'semantic' and 'canonical role' in m.content for m in existing):
            memory.add(new_memory(
                agent.agent_id,
                f'canonical role: {dossier.character.role}; archetype: {dossier.character.archetype}',
                kind='semantic',
                source='canonical_dossier',
                importance=0.9,
                confidence=1.0,
            ))

    relationships.ensure_roster_graph(agent_ids)

    from expansion.migrations import apply_pending
    from expansion.policy import PolicyEngine
    from expansion.rooms import RoomRegistry
    apply_pending(layout)
    RoomRegistry(layout).seed_defaults()
    PolicyEngine(layout).seed_defaults()

    # Persist enriched agents
    for agent in roster:
        path = layout.user_agents / f'default-{agent.agent_id}.json'
        from expansion.schema import to_dict
        import time
        if path.exists():
            try:
                prev = json.loads(path.read_text(encoding='utf-8'))
                if prev.get('created_at'):
                    agent.created_at = prev['created_at']
            except (json.JSONDecodeError, OSError):
                pass
        agent.updated_at = time.time()
        path.write_text(json.dumps(to_dict(agent), indent=2, default=str) + '\n', encoding='utf-8')

    bus.emit(new_event(
        'provision.completed',
        actor='system',
        subject='roster',
        payload={'agents': agent_ids, 'phase': 'p1_bootstrap'},
    ))
    return {
        'agents': agent_ids,
        'emotions': emotions.list_agent_ids(),
        'relationship_files': len(list(layout.user_relationships.glob('*.json'))),
    }


def _sensitivity_for(agent_id: str, dossier) -> dict:
    sens = {}
    sens['jealousy'] = 0.6 + dossier.social.jealousy_sensitivity
    sens['attachment'] = 0.6 + dossier.social.possessiveness * 0.7
    if agent_id == 'aria':
        sens['jealousy'] = 1.55
        sens['attachment'] = 1.4
    elif agent_id == 'muse':
        sens['pride'] = 1.4
        sens['insecurity'] = 1.25
    elif agent_id == 'ledger':
        sens['concern'] = 1.25
        sens['fear'] = 1.2
    elif agent_id == 'vector':
        sens['frustration'] = 1.15
    elif agent_id == 'sentry':
        sens['concern'] = 1.45
        sens['fear'] = 1.3
    return sens
