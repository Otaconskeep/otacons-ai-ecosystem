# -*- coding: utf-8 -*-
"""Public Expansion Hermes layer — behavioral pipeline + personality runtime."""
from expansion.hermes.personality_runtime import (
    build_personality_runtime_packet,
    classify_persona_intent,
    layered_system_prompt_section,
    render_persona_text_via_hermes,
    runtime_enabled,
)
from expansion.hermes.behavioral_policy import (
    BehavioralPolicy,
    build_behavioral_policy,
    classify_behavioral_intent,
)
from expansion.hermes.behavior_pipeline import (
    run_pre_generation,
    run_post_generation,
    run_full_turn_without_llm,
)

__all__ = [
    'BehavioralPolicy',
    'build_behavioral_policy',
    'build_personality_runtime_packet',
    'classify_behavioral_intent',
    'classify_persona_intent',
    'layered_system_prompt_section',
    'render_persona_text_via_hermes',
    'run_full_turn_without_llm',
    'run_post_generation',
    'run_pre_generation',
    'runtime_enabled',
]
