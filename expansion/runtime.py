"""Multi-agent runtime: selection, behavior context assembly, chat prompt enrichment."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.canonical_dossiers import get_canonical_dossier
from expansion.dossier import to_dict as dossier_to_dict
from expansion.emotion_store import EmotionStore
from expansion.memory_bridge import ExpansionMemory
from expansion.relationship_store import RelationshipStore
from expansion.schema import from_dict as agent_from_dict
from expansion.state_layout import StateLayout, resolve_layout


DEFAULT_AGENT_IDS = ('aria', 'vector', 'ledger', 'muse', 'sentry')


@dataclass
class AgentRuntimeView:
    agent_id: str
    display_name: str
    role: str
    domain: str
    archetype: str
    persona: str
    voice_id: str
    room_route: str
    room_title: str
    presentation: str
    motion_manifest_id: str = ''
    motion_capability_level: int = 0


@dataclass
class BehaviorContext:
    agent_id: str
    display_name: str
    personality: str
    archetype: str
    vulnerabilities: list
    emotion: dict
    relationships: list
    memories: list
    dossier_summary: dict
    system_prompt: str
    provenance_hints: dict = field(default_factory=dict)


class ExpansionRuntime:
    def __init__(self, layout: Optional[StateLayout] = None, core_memory=None):
        self.layout = layout or resolve_layout()
        self.emotions = EmotionStore(self.layout)
        self.relationships = RelationshipStore(self.layout)
        self.memory = ExpansionMemory(self.layout, core_store=core_memory)

    def expansion_enabled(self) -> bool:
        return self.layout.user_agents.is_dir() and any(
            self.layout.user_agents.glob('default-*.json')
        )

    def load_roster(self) -> list[AgentRuntimeView]:
        views = []
        for path in sorted(self.layout.user_agents.glob('default-*.json')):
            raw = json.loads(path.read_text(encoding='utf-8'))
            agent = agent_from_dict(raw)
            mm = agent.motion_manifest
            views.append(AgentRuntimeView(
                agent_id=agent.agent_id,
                display_name=agent.display_name,
                role=agent.role,
                domain=agent.domain,
                archetype=agent.archetype,
                persona=agent.persona,
                voice_id=agent.voice.piper_voice,
                room_route=agent.room.route,
                room_title=agent.room.title,
                presentation=agent.presentation,
                motion_manifest_id=(mm.manifest_id if mm else ''),
                motion_capability_level=(mm.capability_level if mm else 0),
            ))
        return views

    def get_agent(self, agent_id: str) -> Optional[AgentRuntimeView]:
        for a in self.load_roster():
            if a.agent_id == agent_id:
                return a
        return None

    def assemble_context(
        self,
        agent_id: str,
        *,
        user_message: str = '',
        memory_limit: int = 5,
    ) -> BehaviorContext:
        view = self.get_agent(agent_id)
        if view is None:
            raise KeyError(f'unknown expansion agent {agent_id}')
        dossier = get_canonical_dossier(agent_id)
        emotion = self.emotions.get_or_create(
            agent_id,
            baseline=dossier.stress.emotional_baseline,
        )
        rels = []
        for rel in self.relationships.all_for(agent_id):
            if rel.source_id != agent_id:
                continue
            # Prefer owner + triangle peers in bounded context
            if rel.target_id not in (
                'user_primary', 'aria', 'muse', 'ledger', 'vector', 'sentry',
            ):
                continue
            rels.append({
                'target': rel.target_id,
                'dimensions': {k: round(v, 4) for k, v in rel.dimensions.items()},
                'provenance_event_ids': list(rel.provenance_event_ids[-5:]),
            })
        memories = [
            {'id': m.memory_id, 'kind': m.kind, 'content': m.content,
             'importance': m.importance, 'event_id': m.event_id}
            for m in self.memory.retrieve(agent_id, user_message or agent_id, limit=memory_limit)
        ]
        vulns = [
            {'kind': v.kind, 'label': v.label, 'intensity': v.intensity,
             'description': v.description}
            for v in dossier.vulnerabilities.items
        ]
        # Living dossier (bounded)
        living_lines = []
        try:
            from expansion.living_dossier import LivingDossierStore
            living = LivingDossierStore(self.layout).load(agent_id)
            for o in living.observations[:5]:
                living_lines.append(f"- {o.category}: {o.value} (conf={o.confidence:.2f})")
        except Exception:
            living_lines = []
        # Active jobs (bounded)
        job_lines = []
        try:
            from expansion.jobs import JobStore
            for j in JobStore(self.layout).list(agent_id=agent_id, limit=5):
                if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED'):
                    job_lines.append(f"- {j.job_id} [{j.status}] {j.request[:80]}")
        except Exception:
            pass
        # Recent journal facts (bounded)
        journal_lines = []
        try:
            from expansion.journal import JournalStore
            for e in JournalStore(self.layout).recent(agent_id=agent_id, limit=3):
                journal_lines.append(f"- {e.summary}")
        except Exception:
            pass
        # Vulnerability activations
        vuln_act_lines = []
        try:
            from expansion.vulnerability_runtime import VulnerabilityRuntime
            acts = VulnerabilityRuntime(self.layout).apply_decay(agent_id).activations
            for label, raw in list(acts.items())[:5]:
                if float(raw.get('intensity') or 0) >= 0.25:
                    vuln_act_lines.append(
                        f"- {label}: intensity={float(raw['intensity']):.2f}"
                    )
        except Exception:
            pass

        top_emotion = sorted(
            emotion.dimensions.items(), key=lambda kv: kv[1], reverse=True,
        )[:6]
        emotion_summary = {k: round(v, 3) for k, v in top_emotion}
        rel_lines = []
        for r in rels[:8]:
            d = r['dimensions']
            rel_lines.append(
                f"- toward {r['target']}: trust={d.get('trust', 0):.2f} "
                f"affinity={d.get('affinity', 0):.2f} jealousy={d.get('jealousy', 0):.2f} "
                f"rivalry={d.get('rivalry', 0):.2f} attachment={d.get('attachment', 0):.2f}"
            )
        mem_lines = [f"- ({m['kind']}) {m['content']}" for m in memories] or ['- (none retrieved)']
        vuln_lines = [f"- {v['kind']}: {v['label']} ({v['intensity']})" for v in vulns]

        system_prompt = (
            f"{view.persona}\n\n"
            f"[Expansion runtime context — stay in character; do not invent owner history]\n"
            f"Archetype: {dossier.character.archetype}\n"
            f"Communication: {dossier.character.communication_style}\n"
            f"Current emotional highlights: {emotion_summary}\n"
            f"Vulnerabilities (influence tone, not competence):\n" + '\n'.join(vuln_lines) + '\n'
            f"Active vulnerability pressure:\n" + '\n'.join(vuln_act_lines or ['- none elevated']) + '\n'
            f"Directional relationships:\n" + '\n'.join(rel_lines or ['- (none)']) + '\n'
            f"Living observations:\n" + '\n'.join(living_lines or ['- none yet']) + '\n'
            f"Active jobs:\n" + '\n'.join(job_lines or ['- none']) + '\n'
            f"Recent journal facts:\n" + '\n'.join(journal_lines or ['- none']) + '\n'
            f"Relevant memory:\n" + '\n'.join(mem_lines) + '\n'
            f"Stress behavior: {dossier.stress.stress_behavior}\n"
        )

        provenance_hints = {
            'jealousy': emotion.explain('jealousy'),
            'stress': emotion.explain('stress'),
            'concern': emotion.explain('concern'),
        }

        return BehaviorContext(
            agent_id=agent_id,
            display_name=view.display_name,
            personality=view.persona,
            archetype=dossier.character.archetype,
            vulnerabilities=vulns,
            emotion={
                'dimensions': {k: round(v, 4) for k, v in emotion.dimensions.items()},
                'updated_at': emotion.updated_at,
            },
            relationships=rels,
            memories=memories,
            dossier_summary={
                'role': dossier.character.role,
                'archetype': dossier.character.archetype,
                'values': list(dossier.character.values),
                'living_observations': living_lines,
            },
            system_prompt=system_prompt,
            provenance_hints=provenance_hints,
        )

    def agent_dict_for_core(self, agent_id: str) -> dict:
        """Shape expected by core.agent_service chat path."""
        view = self.get_agent(agent_id)
        if view is None:
            raise KeyError(agent_id)
        ctx = self.assemble_context(agent_id)
        return {
            'id': view.agent_id,
            'display_name': view.display_name,
            'voice_id': view.voice_id,
            'role': view.role,
            'persona': view.persona,
            'expansion': True,
            'system_prompt': ctx.system_prompt,
            'avatar': f'/assets/{view.agent_id}/{view.agent_id}.webp',
        }
