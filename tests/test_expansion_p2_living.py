"""P2 living + command layer acceptance tests (scenarios A–J)."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.diary import DiaryStore
from expansion.emotion_store import EmotionStore
from expansion.entitlement import EntitlementGate
from expansion.events import new_event
from expansion.jobs import JobStore, route_domain
from expansion.journal import JournalStore
from expansion.living_dossier import LivingDossierStore
from expansion.migrations import apply_pending, load_ledger, snapshot_user_state
from expansion.pipeline import LivingPipeline
from expansion.relationship_interpret import RelationshipInterpreter
from expansion.relationship_store import RelationshipStore
from expansion.reports import build_agent_report
from expansion.rooms import RoomPage, RoomRegistry, ROOM_SCHEMA_VERSION
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout
from expansion.vulnerabilities import VulnerabilityKind
from expansion.vulnerability_runtime import VulnerabilityRuntime


class P2LayoutCase(unittest.TestCase):
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
        self.pipe = LivingPipeline(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()


class TestScenarioA_PraiseMuse(P2LayoutCase):
    def test_praise_muse_jealousy_journal_diary_no_sabotage(self):
        emo = EmotionStore(self.layout)
        before = emo.get('aria').dimensions['jealousy']
        for _ in range(4):
            ev = new_event(
                'user.praised_agent', actor='user', subject='muse',
                payload={'text': 'Muse is brilliant'},
            )
            out = self.pipe.apply_event(ev)
            self.assertTrue(out['journal_ids'])
        after = emo.get('aria')
        self.assertGreater(after.dimensions['jealousy'], before)
        why = after.explain('jealousy')
        self.assertTrue(why['sources'])
        self.assertIn('contributions', why)
        journals = JournalStore(self.layout).recent(agent_id='aria', limit=20)
        self.assertTrue(any('praised' in j.summary.lower() or 'muse' in j.summary.lower()
                            for j in journals))
        diary = DiaryStore(self.layout).recent('aria', limit=5)
        self.assertTrue(diary)
        self.assertTrue(diary[0].get('source_journal_ids'))
        # No operational sabotage — Aria still routes jobs
        job = JobStore(self.layout).create('coordinate status', domain='coordination')
        self.assertEqual(job.assigned_agent, 'aria')
        self.assertEqual(job.status, 'QUEUED')


class TestScenarioB_ReassureAria(P2LayoutCase):
    def test_reassure_reduces_jealousy_with_provenance(self):
        for _ in range(3):
            self.pipe.apply_event(new_event(
                'user.praised_agent', actor='user', subject='muse',
                payload={'text': 'great Muse'},
            ))
        mid = EmotionStore(self.layout).get('aria').dimensions['jealousy']
        ev = new_event(
            'user.praised_agent', actor='user', subject='aria',
            payload={'reassure': True, 'text': 'I still need you'},
        )
        self.pipe.apply_event(ev)
        after = EmotionStore(self.layout).get('aria')
        self.assertLess(after.dimensions['jealousy'], mid)
        self.assertLess(after.dimensions['stress'], mid + 0.5)
        why = after.explain('jealousy')
        self.assertTrue(any(s.get('event_id') == ev.event_id for s in why['sources'])
                        or any('reassur' in (s.get('note') or '') for s in why['sources']))


class TestScenarioC_VectorSuccess(P2LayoutCase):
    def test_vector_success_trust_and_living_dossier(self):
        rels = RelationshipStore(self.layout)
        before = rels.get('aria', 'vector').dimensions['trust']
        for i in range(3):
            out = self.pipe.create_and_run_job(
                f'recover service {i}', domain='infrastructure', succeed=True,
            )
            self.assertEqual(out['job'].status, 'COMPLETE')
            self.assertEqual(out['job'].assigned_agent, 'vector')
        after = rels.get('aria', 'vector')
        self.assertGreater(after.dimensions['trust'], before)
        self.assertGreaterEqual(after.dimensions['reliability'], before)
        living = LivingDossierStore(self.layout).load('vector')
        self.assertTrue(living.observations)
        obs = living.observations[0]
        self.assertTrue(obs.supporting_event_ids or obs.supporting_job_ids)
        explain = LivingDossierStore(self.layout).explain('vector', obs.observation_id)
        self.assertIn('supporting_event_ids', explain)


class TestScenarioD_VectorFailure(P2LayoutCase):
    def test_vector_failures_confidence_anxiety_no_invented_memories(self):
        emo = EmotionStore(self.layout)
        before_c = emo.get('vector').dimensions['confidence']
        for i in range(3):
            self.pipe.create_and_run_job(
                f'deploy fail {i}', domain='systems', succeed=False, error='timeout',
            )
        after = emo.get('vector')
        self.assertLess(after.dimensions['confidence'], before_c)
        vulns = VulnerabilityRuntime(self.layout).load('vector')
        self.assertIn('helplessness/failure', vulns.activations)
        # Journals factual — no fabricated owner meetings
        for j in JournalStore(self.layout).recent(agent_id='vector', limit=20):
            self.assertNotIn('imagined that the owner', j.summary.lower())
        mem_path = self.layout.user_memory / 'vector.jsonl'
        if mem_path.is_file():
            text = mem_path.read_text(encoding='utf-8').lower()
            self.assertNotIn('we met in person', text)


class TestScenarioE_LedgerInconsistency(P2LayoutCase):
    def test_memory_inconsistency_activates_verification(self):
        ev = new_event(
            'agent.message', actor='system', subject='ledger',
            payload={'memory_inconsistency': True, 'result': 'mismatch'},
        )
        out = self.pipe.apply_event(ev)
        self.assertTrue(out['journal_ids'])
        vulns = VulnerabilityRuntime(self.layout).load('ledger')
        self.assertIn('forgetting/corruption', vulns.activations)
        self.assertIn('double-checking', vulns.activations)
        emo = EmotionStore(self.layout).get('ledger')
        self.assertGreater(emo.dimensions['concern'], 0.25)
        j = JournalStore(self.layout).recent(agent_id='ledger', limit=5)[0]
        self.assertIn(ev.event_id, j.event_ids)
        self.assertNotIn('fabricated', j.summary.lower())


class TestScenarioF_SentryMiss(P2LayoutCase):
    def test_sentry_miss_then_decay(self):
        out = self.pipe.create_and_run_job(
            'missed perimeter alert', domain='security', succeed=False, error='late alert',
        )
        self.assertEqual(out['job'].assigned_agent, 'sentry')
        emo = EmotionStore(self.layout).get('sentry')
        fear_after = emo.dimensions['fear']
        self.assertGreater(fear_after, 0.25)
        vulns = VulnerabilityRuntime(self.layout)
        state = vulns.load('sentry')
        self.assertIn('blind spots/unseen threats', state.activations)
        # Force decay by rewinding last_event_at
        for label, raw in state.activations.items():
            raw['last_event_at'] = time.time() - 48 * 3600
            raw['intensity'] = 0.9
            state.activations[label] = raw
        vulns.save(state)
        decayed = vulns.apply_decay('sentry')
        for raw in decayed.activations.values():
            self.assertLess(raw['intensity'], 0.9)


class TestScenarioG_MuseIgnored(P2LayoutCase):
    def test_creative_ignored_insecurity(self):
        before = EmotionStore(self.layout).get('muse').dimensions['insecurity']
        ev = new_event(
            'agent.message', actor='user', subject='muse',
            payload={'creative_ignored': True, 'result': 'ignored'},
        )
        self.pipe.apply_event(ev)
        after = EmotionStore(self.layout).get('muse')
        self.assertGreater(after.dimensions['insecurity'], before)
        acts = VulnerabilityRuntime(self.layout).load('muse').activations
        self.assertIn('being ordinary/ignored', acts)


class TestScenarioH_MuseHelpsAria(P2LayoutCase):
    def test_muse_helps_aria_trust_respect(self):
        rels = RelationshipStore(self.layout)
        before = rels.get('aria', 'muse')
        bt, br, briv = before.dimensions['trust'], before.dimensions['respect'], before.dimensions['rivalry']
        ev = new_event(
            'job.completed', actor='muse', subject='muse',
            payload={
                'job_id': 'job_help1', 'result': 'success',
                'helped_agent': 'aria', 'assigned_by': 'aria',
            },
        )
        self.pipe.apply_event(ev)
        after = rels.get('aria', 'muse')
        self.assertGreater(after.dimensions['trust'], bt)
        self.assertGreater(after.dimensions['respect'], br)
        self.assertLessEqual(after.dimensions['rivalry'], briv)


class TestScenarioI_RestartPersistence(P2LayoutCase):
    def test_restart_preserves_living_state(self):
        self.pipe.apply_event(new_event(
            'user.praised_agent', actor='user', subject='muse',
            payload={'text': 'praise'},
        ))
        self.pipe.create_and_run_job('fix network', domain='systems', succeed=True)
        j_count = len(JournalStore(self.layout).recent(limit=100))
        d_count = len(DiaryStore(self.layout).recent('aria', limit=100))
        jealousy = EmotionStore(self.layout).get('aria').dimensions['jealousy']
        trust = RelationshipStore(self.layout).get('aria', 'vector').dimensions['trust']
        jobs = len(JobStore(self.layout).list(limit=100))
        living_n = len(LivingDossierStore(self.layout).load('vector').observations)

        # Simulate restart: new stores, same layout paths
        pipe2 = LivingPipeline(self.layout)
        self.assertGreaterEqual(len(JournalStore(self.layout).recent(limit=100)), j_count)
        self.assertGreaterEqual(len(DiaryStore(self.layout).recent('aria', limit=100)), d_count)
        self.assertAlmostEqual(
            EmotionStore(self.layout).get('aria').dimensions['jealousy'], jealousy, places=4,
        )
        self.assertAlmostEqual(
            RelationshipStore(self.layout).get('aria', 'vector').dimensions['trust'], trust, places=4,
        )
        self.assertEqual(len(JobStore(self.layout).list(limit=100)), jobs)
        self.assertEqual(
            len(LivingDossierStore(self.layout).load('vector').observations), living_n,
        )
        # New pipeline still works
        pipe2.apply_event(new_event(
            'agent.message', actor='user', subject='ledger', payload={'text': 'ping'},
        ))


class TestScenarioJ_CoreOnly(unittest.TestCase):
    def test_core_only_no_expansion_errors(self):
        # Import expansion modules without layout — should not explode
        from expansion import emotion, events, schema  # noqa: F401
        layout_root = Path(tempfile.mkdtemp())
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(layout_root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(layout_root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(layout_root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            layout = resolve_layout()
            layout.ensure_user_dirs()
            rt = ExpansionRuntime(layout)
            self.assertFalse(rt.expansion_enabled())
            gate = EntitlementGate(layout)
            self.assertTrue(gate.user_data_accessible())
            self.assertFalse(gate.expansion_surfaces_allowed())


class TestJobsRoutingRooms(P2LayoutCase):
    def test_domain_routing_defaults(self):
        self.assertEqual(route_domain('infrastructure'), 'vector')
        self.assertEqual(route_domain('records'), 'ledger')
        self.assertEqual(route_domain('creative'), 'muse')
        self.assertEqual(route_domain('security'), 'sentry')
        self.assertEqual(route_domain('mystery'), 'aria')
        self.assertEqual(route_domain('systems', overrides={'systems': 'ledger'}), 'ledger')

    def test_room_registry_and_page_builder(self):
        reg = RoomRegistry(self.layout)
        rooms = reg.seed_defaults()
        ids = {r.page_id for r in rooms}
        self.assertTrue({
            'aria_command', 'war_room', 'project_rex', 'intel', 'creative', 'ops',
        }.issubset(ids))
        with self.assertRaises(ValueError):
            reg.register_page(RoomPage(
                ROOM_SCHEMA_VERSION, 'evil', 'Evil', '/javascript:alert(1)',
                'aria', 'X', 'bad',
            ))
        with self.assertRaises(ValueError):
            reg.register_page(RoomPage(
                ROOM_SCHEMA_VERSION, 'war_room', 'Dup', '/dup-route',
                'aria', 'X', 'collision',
            ))
        ok = reg.register_page(RoomPage(
            ROOM_SCHEMA_VERSION, 'custom_notes', 'Custom Notes', '/pages/custom-notes',
            'aria', 'CN', 'Allowlisted page',
            kind='page_builder',
        ))
        self.assertEqual(ok.page_id, 'custom_notes')

    def test_agent_report_and_codec_context(self):
        self.pipe.create_and_run_job('patch host', domain='infrastructure', succeed=True)
        report = build_agent_report('vector', self.layout)
        self.assertEqual(report['agent_id'], 'vector')
        self.assertIn('emotion', report)
        self.assertIn('recent_journal', report)
        self.assertIn('emotion_why', report)
        ctx = ExpansionRuntime(self.layout).assemble_context('aria', user_message='status')
        self.assertIn('journal', ctx.system_prompt.lower())
        self.assertNotIn('PACKAGE_KEY', ctx.system_prompt)
        self.assertLess(len(ctx.system_prompt), 12000)

    def test_relationship_why_and_matrix(self):
        self.pipe.apply_event(new_event(
            'user.praised_agent', actor='user', subject='muse', payload={},
        ))
        why = RelationshipInterpreter(self.layout).why('aria', 'muse')
        self.assertIn('dimensions', why)
        self.assertIn('trust', why['dimensions'])
        self.assertIn('rivalry', why['dimensions'])
        self.assertIn('supporting_event_ids', why)

    def test_no_spontaneous_addiction(self):
        vr = VulnerabilityRuntime(self.layout)
        # Usage-like event without canonical addictive tendency label
        got = vr.activate(
            'aria', label='caffeine addiction', delta=0.5,
            event_id='evt_fake', note='should refuse',
        )
        self.assertIsNone(got)
        self.assertNotIn('caffeine addiction', vr.load('aria').activations)

    def test_vulnerability_kinds_include_required(self):
        kinds = {k.value for k in VulnerabilityKind}
        for required in (
            'fear', 'anxiety', 'insecurity', 'self_conscious_area', 'weakness',
            'crutch', 'compulsion', 'addictive_tendency', 'avoidance_behavior',
            'shame_point', 'blind_spot',
        ):
            self.assertIn(required, kinds)

    def test_migration_from_p1_preserves_state(self):
        emo_before = EmotionStore(self.layout).get('aria').dimensions['jealousy']
        rel_before = RelationshipStore(self.layout).get('aria', 'muse').dimensions['rivalry']
        snap = snapshot_user_state(self.layout, label='p2-test')
        self.assertTrue(snap.is_dir())
        plan = apply_pending(self.layout)
        applied_ids = {r['migration_id'] for r in plan.applied}
        self.assertIn('m001_p2_living_layer', applied_ids)
        self.assertAlmostEqual(
            EmotionStore(self.layout).get('aria').dimensions['jealousy'], emo_before, places=5,
        )
        self.assertAlmostEqual(
            RelationshipStore(self.layout).get('aria', 'muse').dimensions['rivalry'],
            rel_before, places=5,
        )
        ledger = load_ledger(self.layout)
        self.assertTrue(ledger.applied)

    def test_journal_query_apis(self):
        out = self.pipe.create_and_run_job('query test', domain='research', succeed=True)
        job_id = out['job'].job_id
        event_id = out['event_id']
        store = JournalStore(self.layout)
        self.assertTrue(store.recent(limit=10))
        self.assertTrue(store.recent(agent_id='ledger', limit=10))
        self.assertTrue(store.by_job(job_id))
        self.assertTrue(store.by_event(event_id))
        now = time.time()
        self.assertTrue(store.by_time(start_ts=now - 3600, end_ts=now + 10, limit=50))

    def test_persist_atomic_write(self):
        from expansion.persist import atomic_write_json, read_json
        path = self.layout.user_data_root / 'atomic_probe.json'
        atomic_write_json(path, {'ok': True, 'n': 1})
        self.assertEqual(read_json(path)['ok'], True)
        atomic_write_json(path, {'ok': True, 'n': 2})
        self.assertEqual(read_json(path)['n'], 2)


if __name__ == '__main__':
    unittest.main()
