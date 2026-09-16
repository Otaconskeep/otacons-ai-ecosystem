"""Persistent emotional state store (user data)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from expansion.emotion import EmotionalState, from_dict, new_emotional_state, to_dict
from expansion.state_layout import StateLayout, resolve_layout


class EmotionStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_emotions.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> Path:
        return self.layout.user_emotions / f'{agent_id}.json'

    def get(self, agent_id: str) -> Optional[EmotionalState]:
        path = self._path(agent_id)
        if not path.is_file():
            return None
        return from_dict(json.loads(path.read_text(encoding='utf-8')))

    def get_or_create(self, agent_id: str, **kwargs) -> EmotionalState:
        existing = self.get(agent_id)
        if existing is not None:
            return existing
        state = new_emotional_state(agent_id, **kwargs)
        self.save(state)
        return state

    def save(self, state: EmotionalState) -> Path:
        path = self._path(state.agent_id)
        path.write_text(json.dumps(to_dict(state), indent=2) + '\n', encoding='utf-8')
        return path

    def list_agent_ids(self) -> list[str]:
        return sorted(p.stem for p in self.layout.user_emotions.glob('*.json'))
