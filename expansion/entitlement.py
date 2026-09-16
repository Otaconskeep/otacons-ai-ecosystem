"""Entitlement interface — Expansion consults this; Core never depends on it.

Fail-open for local user data. No always-online licensing dependency in P2.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class EntitlementState:
    expansion_entitled: bool
    source: str  # local_dev | offline | offline_grace | none
    checked_at: float
    message: str = ''
    grace_until: float = 0.0


class EntitlementGate:
    """Development-default: Expansion entitled locally when agents exist."""

    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self._path = self.layout.user_preferences / 'entitlement.json'

    def current(self) -> EntitlementState:
        raw = read_json(self._path, default=None)
        if raw:
            return EntitlementState(**{k: raw[k] for k in EntitlementState.__dataclass_fields__ if k in raw})
        # Local dev / foundation: entitled if Expansion roster present
        entitled = self.layout.user_agents.is_dir() and any(
            self.layout.user_agents.glob('default-*.json')
        )
        state = EntitlementState(
            expansion_entitled=entitled,
            source='local_dev' if entitled else 'none',
            checked_at=time.time(),
            message='Local Expansion entitlement (no always-online license in P2).',
        )
        atomic_write_json(self._path, asdict(state))
        return state

    def expansion_surfaces_allowed(self) -> bool:
        state = self.current()
        if state.expansion_entitled:
            return True
        # Grace: user data remains accessible even if entitled=false offline
        if state.grace_until and time.time() < state.grace_until:
            return True
        return False

    def user_data_accessible(self) -> bool:
        """User memories/journals/relationships always readable locally."""
        return True
