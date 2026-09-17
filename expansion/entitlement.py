"""Entitlement interface — Expansion consults this; Core never depends on it.

Fail-open for local user data. No always-online licensing dependency in P2.

Lifecycle rule:
  - Explicit license denials (source=license|offline_grace with entitled=false)
    are preserved.
  - Auto-generated source=none (recorded before a roster existed) is recomputed
    when a roster appears so a pre-install UI visit cannot permanently lock
    Expansion surfaces after a successful foundation install.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

# Sources that represent an explicit licensing decision — never auto-upgrade.
_EXPLICIT_DENIAL_SOURCES = frozenset({'license', 'offline_grace', 'revoked'})


@dataclass
class EntitlementState:
    expansion_entitled: bool
    source: str  # local_dev | license | offline_grace | none | revoked
    checked_at: float
    message: str = ''
    grace_until: float = 0.0


class EntitlementGate:
    """Development-default: Expansion entitled locally when agents exist."""

    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self._path = self.layout.user_preferences / 'entitlement.json'

    def _roster_present(self) -> bool:
        return self.layout.user_agents.is_dir() and any(
            self.layout.user_agents.glob('default-*.json')
        )

    def _local_dev_state(self, *, entitled: bool) -> EntitlementState:
        return EntitlementState(
            expansion_entitled=entitled,
            source='local_dev' if entitled else 'none',
            checked_at=time.time(),
            message=(
                'Local Expansion entitlement (no always-online license in P2).'
                if entitled
                else 'No Expansion roster yet — surfaces locked until foundation install.'
            ),
        )

    def current(self) -> EntitlementState:
        raw = read_json(self._path, default=None)
        roster = self._roster_present()
        if raw:
            state = EntitlementState(
                **{k: raw[k] for k in EntitlementState.__dataclass_fields__ if k in raw}
            )
            # Stale auto-deny from a pre-seed visit: recompute once roster exists.
            if (
                state.source == 'none'
                and not state.expansion_entitled
                and roster
            ):
                state = self._local_dev_state(entitled=True)
                atomic_write_json(self._path, asdict(state))
                return state
            # Explicit denials stay denied even if a roster file appears.
            if state.source in _EXPLICIT_DENIAL_SOURCES and not state.expansion_entitled:
                return state
            return state

        state = self._local_dev_state(entitled=roster)
        atomic_write_json(self._path, asdict(state))
        return state

    def refresh_after_provision(self) -> EntitlementState:
        """Call after successful seed/bootstrap. Upgrades stale source=none only."""
        return self.current()

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
