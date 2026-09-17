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
import os
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
    'entitlement',
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
        """Foundation installed: five agents load and validate.

        This is NOT full Expansion usability. Entitlement, writable stores, and
        feature smoke checks gate expansion_ready / surfaces_ready separately.
        """
        needed = ('agents_load', 'registry_validates')
        return all(self.semantic.get(c) == ReadinessState.READY for c in needed)

    def expansion_entitled(self) -> bool:
        return self.semantic.get('entitlement') == ReadinessState.READY

    def surfaces_ready(self) -> bool:
        """Foundation + entitlement: entitled surfaces may be opened."""
        return self.foundation_ready() and self.expansion_entitled()

    def expansion_ready(self) -> bool:
        """End-to-end Expansion banner: entitled, writable core stores, codec path."""
        if not self.surfaces_ready():
            return False
        needed = (
            'relationship_store',
            'emotion_engine',
            'memory_store',
            'journal_write',
            'codec_reaches_agent',
        )
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
            'expansion_entitled': self.expansion_entitled(),
            'surfaces_ready': self.surfaces_ready(),
            'expansion_ready': self.expansion_ready(),
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

    # Entitlement — required before advertising entitled surfaces as usable
    try:
        from expansion.entitlement import EntitlementGate
        ent = EntitlementGate(layout).current()
        if ent.expansion_entitled:
            report.set_semantic(
                'entitlement',
                ReadinessState.READY,
                f'source={ent.source}',
            )
        else:
            report.set_semantic(
                'entitlement',
                ReadinessState.FAILED,
                ent.message or f'not entitled (source={ent.source})',
            )
    except Exception as exc:  # noqa: BLE001
        report.set_semantic('entitlement', ReadinessState.FAILED, str(exc))

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

    report.set_semantic('relationship_store',
                        ReadinessState.READY if any(layout.user_relationships.glob('*.json'))
                        and os.access(layout.user_relationships, os.W_OK)
                        else ReadinessState.NOT_CONFIGURED)
    report.set_semantic('emotion_engine',
                        ReadinessState.READY if any(layout.user_emotions.glob('*.json'))
                        and os.access(layout.user_emotions, os.W_OK)
                        else ReadinessState.NOT_CONFIGURED)
    report.set_semantic('memory_store',
                        ReadinessState.READY if any(layout.user_memory.glob('*'))
                        and os.access(layout.user_memory, os.W_OK)
                        else ReadinessState.NOT_CONFIGURED)
    # journal_write: require a writable journals dir (empty seed files alone are not proof)
    journals_ok = (
        layout.user_journals.is_dir()
        and os.access(layout.user_journals, os.W_OK)
        and any(layout.user_journals.glob('*.jsonl'))
    )
    report.set_semantic(
        'journal_write',
        ReadinessState.READY if journals_ok else ReadinessState.NOT_CONFIGURED,
        'writable journal files present' if journals_ok else 'journals missing or not writable',
    )
    report.set_semantic('diary_generate', ReadinessState.LIMITED,
                        'diary stores exist; generation heuristics are P2')
    report.set_semantic('job_execution',
                        ReadinessState.LIMITED if layout.user_jobs.exists()
                        else ReadinessState.NOT_CONFIGURED)
    report.set_semantic(
        'rooms_register',
        ReadinessState.READY if agents and all((a.get('room') or {}).get('route') for a in agents)
        else ReadinessState.NOT_CONFIGURED,
    )
    # Codec reaches agent when roster is loadable via Expansion runtime
    try:
        from expansion.runtime import ExpansionRuntime
        rt = ExpansionRuntime(layout)
        codec_ok = rt.expansion_enabled() and len(rt.load_roster()) >= 5
        report.set_semantic(
            'codec_reaches_agent',
            ReadinessState.READY if codec_ok else ReadinessState.NOT_CONFIGURED,
            'roster-aware Codec path available' if codec_ok else 'Expansion roster missing',
        )
    except Exception as exc:
        report.set_semantic('codec_reaches_agent', ReadinessState.FAILED, str(exc))

    # Motion manifests validate
    try:
        from expansion.motion_defaults import validated_default_manifests
        validated_default_manifests()
        report.set('MOTION', ReadinessState.READY)
    except Exception as exc:
        report.set('MOTION', ReadinessState.FAILED)
        report.details['motion'] = str(exc)

    if report.semantic.get('emotion_engine') == ReadinessState.READY:
        report.set('EMOTIONAL_ENGINE', ReadinessState.READY)
    if report.semantic.get('relationship_store') == ReadinessState.READY:
        report.set('RELATIONSHIPS', ReadinessState.READY)

    report.set_semantic('protected_bundle', ReadinessState.NOT_CONFIGURED,
                        'protected release pipeline available via expansion.release')

    # Optional components — probe without failing foundation
    try:
        from expansion.capabilities.discord_n8n import probe_all_optional
        caps = probe_all_optional(layout)
        mapping = {
            'VIDEO_STUDIO': caps['video_studio']['state'],
            'HOME_ASSISTANT': caps['home_assistant']['state'],
            'DISCORD': caps['discord']['state'],
            'N8N': caps['n8n']['state'],
        }
        for name, state in mapping.items():
            try:
                report.set(name, ReadinessState(state))
            except ValueError:
                report.set(name, ReadinessState.UNAVAILABLE)
    except Exception as exc:  # noqa: BLE001
        for name in ('VIDEO_STUDIO', 'HOME_ASSISTANT', 'DISCORD', 'N8N'):
            if name not in report.components:
                report.set(name, ReadinessState.UNAVAILABLE)
        report.details['optional_capabilities'] = str(exc)

    # Remaining optionals default
    for name in OPTIONAL_COMPONENTS:
        if name not in report.components:
            report.set(name, ReadinessState.NOT_CONFIGURED)

    return report
