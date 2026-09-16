"""P1 runtime spine acceptance tests.

Proves emotion/relationship persistence, event-driven dynamics with
provenance, memory retrieval, dossiers, motion, context assembly, and
Core-only safety (Expansion modules import without requiring Keep).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.canonical_dossiers import all_canonical_dossiers, get_canonical_dossier
from expansion.dossier import validate_canonical_dossier
from expansion.emotion_store import EmotionStore
from expansion.event_effects import emit_and_apply
from expansion.events import new_event
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.motion_defaults import validated_default_manifests
from expansion.relationship_store import RelationshipStore
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout
from expansion.canonical_dossiers import get_canonical_dossier as load_dossier


class P1LayoutCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()


class TestCanonicalDossiers(P1LayoutCase):
    def test_all_five_validate(self):
        for agent_id, d in all_canonical_dossiers().items():
            self.assertEqual(validate_canonical_dossier(d), [], agent_id)

    def test_aria_vulnerability_profile(self):
        d = get_canonical_dossier('aria')
        kinds = {v.kind for v in d.vulnerabilities.items}
        self.assertIn('fear', kinds)
        self.assertIn('crutch', kinds)
        self.assertIn('compulsion', kinds)
        self.assertGreaterEqual(d.social.jealousy_sensitivity, 0.8)


class TestMotionAndBootstrap(P1LayoutCase):
    def test_motion_manifests_validate(self):
        validated_default_manifests()

    def test_five_agents_load_from_dossiers(self):
        rt = ExpansionRuntime(self.layout)
        roster = rt.load_roster()
        self.assertEqual({a.agent_id for a in roster},
                         {'aria', 'vector', 'ledger', 'muse', 'sentry'})
        for a in roster:
            self.assertTrue(a.motion_manifest_id)
            self.assertTrue(a.voice_id)


class TestEmotionRelationshipDynamics(P1LayoutCase):
    def test_praise_muse_raises_aria_jealousy_with_provenance(self):
        emo = EmotionStore(self.layout)
        before = emo.get('aria').dimensions['jealousy']
        event_ids = []
        for _ in range(3):
            ev = new_event('user.praised_agent', actor='user', subject='muse',
                           payload={'text': 'Muse is brilliant'})
            event_ids.append(ev.event_id)
            emit_and_apply(ev, layout=self.layout, dossier_loader=load_dossier)
        after = emo.get('aria')
        self.assertGreater(after.dimensions['jealousy'], before)
        explain = after.explain('jealousy')
        self.assertTrue(explain['sources'])
        src_ids = {s['event_id'] for s in explain['sources']}
        self.assertTrue(src_ids & set(event_ids))

    def test_vector_job_completed_raises_aria_trust(self):
        rels = RelationshipStore(self.layout)
        before = rels.get('aria', 'vector').dimensions['trust']
        ev = new_event('job.completed', actor='vector', subject='vector',
                       payload={'job': 'fix-nginx'})
        emit_and_apply(ev, layout=self.layout, dossier_loader=load_dossier)
        after = rels.get('aria', 'vector')
        self.assertGreater(after.dimensions['trust'], before)
        self.assertIn(ev.event_id, after.provenance_event_ids)

    def test_reassure_aria_lowers_jealousy_and_stress(self):
        emo = EmotionStore(self.layout)
        # Spike jealousy first
        for _ in range(2):
            emit_and_apply(
                new_event('user.praised_agent', actor='user', subject='muse'),
                layout=self.layout, dossier_loader=load_dossier,
            )
        spiked = emo.get('aria')
        j0, s0 = spiked.dimensions['jealousy'], spiked.dimensions['stress']
        emit_and_apply(
            new_event('user.praised_agent', actor='user', subject='aria',
                      payload={'reassure': True, 'text': 'You are still first'}),
            layout=self.layout, dossier_loader=load_dossier,
        )
        calm = emo.get('aria')
        self.assertLess(calm.dimensions['jealousy'], j0)
        self.assertLess(calm.dimensions['stress'], s0)

    def test_sentry_job_failed_raises_concern(self):
        emo = EmotionStore(self.layout)
        before = emo.get('sentry').dimensions['concern']
        emit_and_apply(
            new_event('job.failed', actor='sentry', subject='sentry',
                      payload={'alert': 'perimeter'}),
            layout=self.layout, dossier_loader=load_dossier,
        )
        after = emo.get('sentry')
        self.assertGreater(after.dimensions['concern'], before)
        self.assertGreater(after.dimensions['fear'], emo.get('sentry').baseline.get('fear', 0))

    def test_persist_across_store_reload(self):
        emo = EmotionStore(self.layout)
        rels = RelationshipStore(self.layout)
        emit_and_apply(
            new_event('user.praised_agent', actor='user', subject='muse'),
            layout=self.layout, dossier_loader=load_dossier,
        )
        j1 = emo.get('aria').dimensions['jealousy']
        t1 = rels.get('aria', 'muse').dimensions['jealousy']
        # New store instances = restart simulation
        emo2 = EmotionStore(self.layout)
        rels2 = RelationshipStore(self.layout)
        self.assertAlmostEqual(emo2.get('aria').dimensions['jealousy'], j1, places=5)
        self.assertAlmostEqual(rels2.get('aria', 'muse').dimensions['jealousy'], t1, places=5)


class TestMemoryAndContext(P1LayoutCase):
    def test_memory_retrieval_per_agent(self):
        mem = ExpansionMemory(self.layout)
        mem.add(new_memory('vector', 'prefers infrastructure runbooks', kind='important',
                           importance=0.9))
        mem.add(new_memory('muse', 'hates bland color palettes', kind='semantic',
                           importance=0.8))
        hits = mem.retrieve('vector', 'infrastructure runbook', limit=3)
        self.assertTrue(hits)
        self.assertTrue(all(h.agent_id == 'vector' for h in hits))
        muse_hits = mem.retrieve('muse', 'color palette', limit=3)
        self.assertTrue(muse_hits)

    def test_behavior_context_includes_required_fields(self):
        rt = ExpansionRuntime(self.layout)
        ctx = rt.assemble_context('aria', user_message='status')
        self.assertIn('jealousy', ctx.emotion['dimensions'])
        self.assertTrue(ctx.vulnerabilities)
        self.assertTrue(ctx.personality)
        self.assertIn('Archetype', ctx.system_prompt)
        self.assertIn('Current emotional highlights', ctx.system_prompt)
        self.assertIn('Directional relationships', ctx.system_prompt)
        # system prompt must include vulnerability influence note
        self.assertIn('Vulnerabilities', ctx.system_prompt)


class TestProvisionFilled(P1LayoutCase):
    def test_provision_completes_with_real_stores(self):
        from expansion.provision import provision_agent
        from expansion.seed_defaults import build_default_roster
        # Re-provision aria into same layout
        aria = build_default_roster()[0]
        tx = provision_agent(aria, layout=self.layout)
        self.assertEqual(tx.status, 'completed')
        deferred = [s for s in tx.steps if s.get('deferred')]
        # emotion/relationship/dossier/journal/motion should not be deferred now
        non_deferred_required = {
            'emotional_state_init', 'relationship_graph_init', 'dossier_init',
            'journal_init', 'motion_manifest', 'greeting_fast_path',
        }
        done = {s['step'] for s in tx.steps if s['status'] == 'completed'}
        self.assertTrue(non_deferred_required.issubset(done))


class TestCoreOnlyUntouched(unittest.TestCase):
    def test_system_prompt_core_path(self):
        from core.agent_service import system_prompt
        self.assertIn('local AI assistant', system_prompt({'display_name': 'Aria'}))

    def test_expansion_system_prompt_override(self):
        from core.agent_service import system_prompt
        self.assertEqual(
            system_prompt({'display_name': 'Aria', 'system_prompt': 'EXPANSION CTX'}),
            'EXPANSION CTX',
        )

    def test_private_keep_not_used_as_default(self):
        from expansion.topology import default_topology, shell_public_install_probe
        cfg = default_topology()
        self.assertEqual(cfg.validate(), [])
        self.assertNotIn('/opt/otacon', cfg.ollama_url)
        probe = shell_public_install_probe()
        self.assertNotIn('/opt/otacon', probe)
        self.assertIn('otacon-ai-ecosystem}/core', probe)


if __name__ == '__main__':
    unittest.main()
