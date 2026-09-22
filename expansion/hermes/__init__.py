# -*- coding: utf-8 -*-
"""Public Expansion Hermes layer — personality runtime (clean-room)."""
from expansion.hermes.personality_runtime import (
    build_personality_runtime_packet,
    classify_persona_intent,
    layered_system_prompt_section,
    render_persona_text_via_hermes,
    runtime_enabled,
)

__all__ = [
    'build_personality_runtime_packet',
    'classify_persona_intent',
    'layered_system_prompt_section',
    'render_persona_text_via_hermes',
    'runtime_enabled',
]
