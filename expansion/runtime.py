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
        # Learning engine (private + shared claims) — not the same as memory
        learn_lines = []
        try:
            from expansion.learning import LearningEngine
            learn_lines = LearningEngine(self.layout).context_lines(agent_id, limit=6)
        except Exception:
            learn_lines = []
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

        # Turing spine — biography/taste/speech ride every subjective turn
        who_block = ''
        self_state_line = ''
        praise_line = ''
        affect_lines: list[str] = []
        try:
            from expansion.humanization import (
                dossier_prompt_block,
                spoken_self_state,
                praise_language_directive,
                affect_presence_lines,
            )
            who_block = dossier_prompt_block(agent_id, layout=self.layout)
            self_state_line = spoken_self_state(
                emotion.dimensions, agent_id=agent_id,
            )
            praise_line = praise_language_directive(user_message)
            affect_lines = affect_presence_lines(emotion.dimensions)
        except Exception:
            who_block = ''

        who_section = (who_block + '\n\n') if who_block else ''
        self_section = (
            f"How you feel right now (speak this, never dump numbers): {self_state_line}\n"
            if self_state_line else ''
        )
        praise_section = (praise_line + '\n') if praise_line else ''
        affect_section = (
            'Affect presence (long vs short — feel both):\n'
            + '\n'.join(affect_lines) + '\n'
            if affect_lines else ''
        )

        # Keep-parity clean-room spine: anti-briefing + work mode + layered IQ
        work_section = ''
        delivery_section = ''
        layered_section = ''
        hermes_section = ''
        dual_affect = ''
        try:
            from expansion.behavior_spine import (
                work_mode_directive,
                delivery_rules_block,
                layered_intelligence_block,
            )
            work_section = work_mode_directive(user_message or '')
            delivery_section = delivery_rules_block(agent_id=agent_id) + '\n'
            layered_section = layered_intelligence_block(
                emotion_summary=str(emotion_summary),
                learn_lines=learn_lines,
                journal_lines=journal_lines,
            )
        except Exception:
            pass
        # Dual-affect + Hermes prompt blocks ONLY here.
        # Mutations run once in chat_learning.before_reply / Hermes pipeline.
        try:
            from expansion.continuity.conversational_affect import (
                build_dual_affect_prompt_block,
            )
            dual_affect = build_dual_affect_prompt_block(
                agent_id, layout=self.layout,
            )
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('context_assembly', exc, detail='dual_affect')
            dual_affect = ''
        try:
            from expansion.hermes.personality_runtime import layered_system_prompt_section
            hermes_section = layered_system_prompt_section(
                agent_id, user_message or '', layout=self.layout,
            )
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('context_assembly', exc, detail='hermes_section')
            hermes_section = ''
        policy_section = ''
        try:
            from expansion.hermes.behavioral_policy import build_behavioral_policy
            from expansion.continuity.emotion_bridge import get_emotion_vector, load_bond
            from expansion.continuity.relationship import RelationshipEngine
            vec = get_emotion_vector(agent_id, layout=self.layout)
            bond = load_bond(agent_id, layout=self.layout)
            level = RelationshipEngine.operator_rel_level(agent_id, layout=self.layout)
            policy_section = build_behavioral_policy(
                user_message or '',
                agent_id=agent_id,
                emotion_vector=vec,
                bond=bond,
                operator_rel_level=level,
            ).to_prompt_block()
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('hermes', exc, detail='policy_section')
            policy_section = ''

        # Formula 5 relationship summary + Formula 9 scored memory
        f5_section = ''
        f9_section = ''
        try:
            from expansion.continuity.relationship import RelationshipEngine
            f5_section = RelationshipEngine.relationship_summary_for_prompt(
                agent_id, layout=self.layout,
            )
            if f5_section:
                f5_section = f5_section + '\n'
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('relationship_engine', exc, detail='assemble')
            f5_section = ''
        try:
            from expansion.continuity.memory_engine import MemoryEngine
            f9_section = MemoryEngine.memory_prompt_block(
                agent_id, user_message or '', top_k=memory_limit, layout=self.layout,
            )
            if f9_section:
                mem_lines = [
                    ln for ln in f9_section.splitlines() if ln.startswith('- ')
                ] or mem_lines
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('memory_engine', exc, detail='assemble')
            f9_section = ''
        try:
            from expansion.continuity.state_engine import StateEngine
            state_section = StateEngine.summary_for_prompt(
                agent_id, layout=self.layout,
            ) + '\n'
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('state_engine', exc, detail='assemble')
            state_section = ''
        prefs_section = ''
        try:
            from expansion.continuity.preferences import PreferenceStore
            prefs_section = PreferenceStore(self.layout).prompt_block(agent_id)
        except Exception as exc:
            from expansion.continuity.health import record_failure
            record_failure('preferences', exc, detail='assemble')

        system_prompt = (
            f"{view.persona}\n\n"
            f"{who_section}"
            f"{delivery_section}"
            f"{work_section}"
            f"{policy_section}"
            f"{hermes_section}"
            f"{dual_affect}"
            f"{layered_section}"
            f"{state_section}"
            f"{f5_section}"
            f"{prefs_section}"
            f"[Expansion runtime context — stay in character; do not invent owner history]\n"
            f"Voice rules: never sound like a generic AI assistant. Never say "
            f"\"happy to help\", \"as an AI\", \"certainly\", \"I'd be glad to\", "
            f"\"Greetings\", or dump emotion percentages. Speak as this person. "
            f"Prefer concrete specifics and usable plans over stock helpfulness "
            f"or Keep/ops continuity speeches.\n"
            f"Archetype: {dossier.character.archetype}\n"
            f"Communication: {dossier.character.communication_style}\n"
            f"{self_section}"
            f"{affect_section}"
            f"{praise_section}"
            f"Current emotional highlights (internal — do not recite as telemetry): {emotion_summary}\n"
            f"Vulnerabilities (influence tone, not competence):\n" + '\n'.join(vuln_lines) + '\n'
            f"Active vulnerability pressure:\n" + '\n'.join(vuln_act_lines or ['- none elevated']) + '\n'
            f"Directional relationships:\n" + '\n'.join(rel_lines or ['- (none)']) + '\n'
            f"Living observations:\n" + '\n'.join(living_lines or ['- none yet']) + '\n'
            f"Learned claims (evidence-backed; revisable):\n" + '\n'.join(learn_lines or ['- none yet']) + '\n'
            f"Active jobs:\n" + '\n'.join(job_lines or ['- none']) + '\n'
            f"Recent journal facts:\n" + '\n'.join(journal_lines or ['- none']) + '\n'
            f"Relevant memory (Formula 9 when available):\n" + '\n'.join(mem_lines) + '\n'
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
                'learned_claims': learn_lines,
            },
            system_prompt=system_prompt,
            provenance_hints=provenance_hints,
        )

    def agent_dict_for_core(self, agent_id: str) -> dict:
        """Shape expected by core.agent_service chat path."""
        from core.voice import catalog_id_for_piper

        view = self.get_agent(agent_id)
        if view is None:
            raise KeyError(agent_id)
        ctx = self.assemble_context(agent_id)
        voice_id = catalog_id_for_piper(view.voice_id)
        return {
            'id': view.agent_id,
            'display_name': view.display_name,
            'voice_id': voice_id,
            'role': view.role,
            'persona': view.persona,
            'expansion': True,
            'system_prompt': ctx.system_prompt,
            'avatar': f'/assets/{view.agent_id}/{view.agent_id}.webp',
            'room': view.room_route,
            'room_title': view.room_title,
        }
