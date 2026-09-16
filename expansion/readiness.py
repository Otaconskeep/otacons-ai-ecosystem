"""Machine-readable readiness state for the Otacon Expansion Dashboard.

Required components must all read READY for the Dashboard to call itself
healthy. Optional components (Discord, Home Assistant, Video Studio, n8n,
the infra dashboard, Page Builder) never block that -- one optional
subsystem being down must never make the rest look broken.

A live port or HTTP 200 is not sufficient. Semantic checks below are the
Expansion install authority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout


class ReadinessState(str, Enum):
    READY = 'READY'
    LIMITED = 'LIMITED'
    NOT_CONFIGURED = 'NOT_CONFIGURED'
    OFFLINE = 'OFFLINE'
    DEGRADED = 'DEGRADED'
    UNAVAILABLE = 'UNAVAILABLE'
    FAILED = 'FAILED'


REQUIRED_COMPONENTS = (
    'CORE', 'AGENTS', 'VOICE', 'EMOTIONAL_ENGINE', 'RELATIONSHIPS',
)
OPTIONAL_COMPONENTS = (
    'MOTION', 'VIDEO_STUDIO', 'DISCORD', 'HOME_ASSISTANT', 'N8N',
    'INFRA_DASHBOARD', 'PAGE_BUILDER',
)

# P0 semantic checklist names (install authority).
SEMANTIC_CHECKS = (
    'agents_load',
    'registry_validates',
    'relationship_store',
    'emotion_engine',
    'memory_store',
    'journal_write',
    'diary_generate',
    'job_execution',
    'rooms_register',
    'codec_reaches_agent',
    'protected_bundle',
    'restart_survives',
)

DEFAULT_AGENT_IDS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})


@dataclass
class ReadinessReport:
    components: dict = field(default_factory=dict)  # name -> ReadinessState
    semantic: dict = field(default_factory=dict)    # check -> ReadinessState
    details: dict = field(default_factory=dict)

    def set(self, name: str, state: ReadinessState) -> None:
        self.components[name] = state

    def set_semantic(self, name: str, state: ReadinessState, detail: str = '') -> None:
        self.semantic[name] = state
        if detail:
            self.details[name] = detail

    def overall_core_ready(self) -> bool:
        return all(self.components.get(c) == ReadinessState.READY for c in REQUIRED_COMPONENTS)

    def foundation_ready(self) -> bool:
        """P0 foundation: five agents load and validate; stores scaffolding present."""
        needed = ('agents_load', 'registry_validates')
        return all(self.semantic.get(c) == ReadinessState.READY for c in needed)

    def to_dict(self) -> dict:
        components = {
            k: (v.value if isinstance(v, ReadinessState) else v)
            for k, v in self.components.items()
        }
        semantic = {
            k: (v.value if isinstance(v, ReadinessState) else v)
            for k, v in self.semantic.items()
        }
        # Top-level component keys preserved for callers/tests that predate
        # the nested semantic report shape.
        out = dict(components)
        out.update({
            'components': components,
            'semantic': semantic,
            'details': dict(self.details),
            'overall_core_ready': self.overall_core_ready(),
            'foundation_ready': self.foundation_ready(),
        })
        return out


def _load_agent_files(agents_dir: Path) -> list[dict]:
    if not agents_dir.is_dir():
        return []
    out = []
    for path in sorted(agents_dir.glob('default-*.json')):
        try:
            out.append(json.loads(path.read_text(encoding='utf-8')))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def evaluate_foundation(layout: Optional[StateLayout] = None) -> ReadinessReport:
    """Run P0 semantic readiness against the current user-state layout."""
    from expansion.hierarchy import find_cycle
    from expansion.schema import from_dict, validate_agent
    from expansion.topology import public_core_install_present

    layout = layout or resolve_layout()
    report = ReadinessReport()

    # CORE — public markers only
    markers = public_core_install_present()
    if markers.get('any_public_marker'):
        report.set('CORE', ReadinessState.READY)
        report.set_semantic('restart_survives', ReadinessState.NOT_CONFIGURED,
                            'post-restart health check not yet automated in P0')
    else:
        report.set('CORE', ReadinessState.NOT_CONFIGURED)
        report.set_semantic('restart_survives', ReadinessState.NOT_CONFIGURED)

    agents = _load_agent_files(layout.user_agents)
    ids = {a.get('agent_id') for a in agents}
    if DEFAULT_AGENT_IDS.issubset(ids):
        report.set('AGENTS', ReadinessState.READY)
        report.set_semantic('agents_load', ReadinessState.READY, f'{len(agents)} agent files')
    elif agents:
        report.set('AGENTS', ReadinessState.DEGRADED)
        report.set_semantic('agents_load', ReadinessState.DEGRADED, f'partial roster: {sorted(ids)}')
    else:
        report.set('AGENTS', ReadinessState.NOT_CONFIGURED)
        report.set_semantic('agents_load', ReadinessState.NOT_CONFIGURED, 'no default-*.json')

    # Registry validation
    validation_errors = []
    graph = {}
    for raw in agents:
        try:
            agent = from_dict(raw)
            errs = validate_agent(agent)
            validation_errors.extend(errs)
            graph[agent.agent_id] = agent.reporting_to
        except Exception as exc:  # noqa: BLE001
            validation_errors.append(str(exc))
    cycle = find_cycle(graph) if graph else None
    if agents and not validation_errors and cycle is None:
        report.set_semantic('registry_validates', ReadinessState.READY)
    elif agents:
        report.set_semantic(
            'registry_validates',
            ReadinessState.FAILED,
            '; '.join(validation_errors) or f'cycle={cycle}',
        )
    else:
        report.set_semantic('registry_validates', ReadinessState.NOT_CONFIGURED)

    # Voice — bound in schema; onnx verify deferred
    if agents and all((a.get('voice') or {}).get('piper_voice') for a in agents):
        report.set('VOICE', ReadinessState.LIMITED)
    else:
        report.set('VOICE', ReadinessState.NOT_CONFIGURED)

    # Engines / stores — scaffolding dirs vs full engines
    def _dir_state(path: Path, empty_is: ReadinessState = ReadinessState.NOT_CONFIGURED) -> ReadinessState:
        if not path.exists():
            return empty_is
        return ReadinessState.LIMITED  # present but engine not fully wired in P0

    report.set('EMOTIONAL_ENGINE', _dir_state(layout.user_emotions))
    report.set('RELATIONSHIPS', _dir_state(layout.user_relationships))
    report.set_semantic('relationship_store', _dir_state(layout.user_relationships))
    report.set_semantic('emotion_engine', _dir_state(layout.user_emotions))
    report.set_semantic('memory_store', _dir_state(layout.user_memory))
    report.set_semantic('journal_write', _dir_state(layout.user_journals))
    report.set_semantic('diary_generate', ReadinessState.NOT_CONFIGURED,
                        'diary generation is P2')
    report.set_semantic('job_execution', _dir_state(layout.user_jobs))
    report.set_semantic(
        'rooms_register',
        ReadinessState.READY if agents and all((a.get('room') or {}).get('route') for a in agents)
        else ReadinessState.NOT_CONFIGURED,
    )
    report.set_semantic('codec_reaches_agent', ReadinessState.NOT_CONFIGURED,
                        'multi-agent Codec is P1')
    report.set_semantic('protected_bundle', ReadinessState.NOT_CONFIGURED,
                        'protected release pipeline is P2+')

    # Optional components default to NOT_CONFIGURED
    for name in OPTIONAL_COMPONENTS:
        report.set(name, ReadinessState.NOT_CONFIGURED)

    return report
