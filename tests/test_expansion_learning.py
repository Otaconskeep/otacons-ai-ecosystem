"""P5 Learning Engine — evidence-backed claims, not memory/dossier/emotion."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.learning import (
    PATTERN_THRESHOLD,
    LearningEngine,
    ingest_owner_message,
    ingest_operational_success,
    learn_from_autonomy_outcome,
)
from expansion.jobs import JobStore
from expansion.rex import queue_rex_job, verification_ready
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout
from installer.security import path_is_protected


class LearningEngineCase(unittest.TestCase):
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
        self.eng = LearningEngine(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def test_weak_evidence_does_not_graduate(self):
        obs = self.eng.observe(
            'ledger', 'owner prefers concise technical summaries',
            learning_type='owner_preference', evidence_ids=['ev1'],
            scope='shared', actor='ledger',
        )
        self.assertTrue(obs.observation_id)
        claims = self.eng.store.list_claims(
            scope='shared', learning_type='owner_preference',
        )
        self.assertEqual(len(claims), 0)

    def test_pattern_graduation_and_reinforce(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='please keep it concise', event_id=f'ev_c_{i}', actor='ledger',
            )
        claims = self.eng.store.list_claims(scope='shared', learning_type='owner_preference')
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertIn('concise', claim.claim)
        before = claim.confidence
        self.assertTrue(claim.positive_evidence)
        reinforced = self.eng.reinforce(claim.claim_id, 'ev_extra', actor='ledger')
        self.assertGreater(reinforced.confidence, before)
        self.assertIn('ev_extra', reinforced.positive_evidence)

    def test_contradict_revise_and_negative_evidence(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='brief please', event_id=f'ev_b_{i}', actor='ledger',
            )
        claim = self.eng.store.list_claims(
            scope='shared', learning_type='owner_preference',
        )[0]
        hit = self.eng.contradict(claim.claim_id, 'ev_contra', actor='ledger')
        self.assertIn('ev_contra', hit.negative_evidence)
        self.assertGreater(hit.contradiction_count, 0)
        self.assertLess(hit.confidence, claim.confidence)
        revised = self.eng.revise(
            claim.claim_id,
            'owner prefers detailed thorough explanations',
            actor='ledger',
            evidence_id='ev_revise',
        )
        self.assertIn('detailed', revised.claim)
        self.assertTrue(revised.revision_history)

    def test_decay(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='concise bullets', event_id=f'ev_d_{i}', actor='ledger',
            )
        claim = self.eng.store.list_claims(
            scope='shared', learning_type='owner_preference', include_decayed=False,
        )[0]
        claim.last_reinforced = time.time() - (claim.half_life_s * 2)
        claim.last_updated = claim.last_reinforced
        self.eng._write_claim(claim)
        n = self.eng.apply_decay(now=time.time())
        self.assertGreaterEqual(n, 1)
        faded = self.eng.store.get_claim(claim.claim_id)
        self.assertLess(faded.confidence, 0.55)

    def test_why_provenance(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='short summary please', event_id=f'ev_w_{i}', actor='ledger',
            )
        claim = self.eng.store.list_claims(
            scope='shared', learning_type='owner_preference',
        )[0]
        why = self.eng.why(claim.claim_id)
        self.assertEqual(why['claim_id'], claim.claim_id)
        self.assertIn('positive_evidence', why)
        self.assertIn('supporting_observations', why)
        self.assertIn('separations', why)
        self.assertEqual(why['separations']['learning'].split()[0], 'patterned')

    def test_private_vs_shared_no_leak(self):
        for i in range(PATTERN_THRESHOLD):
            self.eng.observe(
                'muse',
                'owner likes playful creative openings',
                learning_type='social',
                evidence_ids=[f'muse_ev_{i}'],
                scope='private',
                actor='muse',
            )
        for i in range(PATTERN_THRESHOLD):
            self.eng.observe(
                'ledger',
                'shared coding convention: prefer typed public APIs',
                learning_type='task',
                evidence_ids=[f'share_ev_{i}'],
                scope='shared',
                actor='ledger',
            )
        muse_surf = self.eng.agent_learning_surface('muse')
        vector_surf = self.eng.agent_learning_surface('vector')
        muse_priv = [c['claim'] for c in muse_surf['private']]
        vector_priv = [c['claim'] for c in vector_surf['private']]
        self.assertTrue(any('playful' in c for c in muse_priv))
        self.assertFalse(any('playful' in c for c in vector_priv))
        self.assertTrue(any('typed public' in c['claim'] for c in vector_surf['shared_keep']))

    def test_duplicate_observation_handling(self):
        a = self.eng.observe(
            'ledger', 'owner prefers concise technical summaries',
            learning_type='owner_preference', evidence_ids=['same_ev'],
            scope='shared', actor='ledger',
        )
        b = self.eng.observe(
            'ledger', 'owner prefers concise technical summaries',
            learning_type='owner_preference', evidence_ids=['same_ev'],
            scope='shared', actor='ledger',
        )
        self.assertEqual(a.observation_id, b.observation_id)
        obs = self.eng.store.list_observations(scope='shared')
        keys = [o.pattern_key for o in obs]
        self.assertEqual(keys.count(a.pattern_key), 1)

    def test_operational_learning_and_autonomy_feed(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_operational_success(
                self.eng,
                method='restart-then-reprobe',
                domain='infrastructure',
                job_id=f'job_op_{i}',
                actor='vector',
            )
        claims = self.eng.store.list_claims(scope='shared', learning_type='operational')
        self.assertEqual(len(claims), 1)
        job = queue_rex_job('repair docker', domain='infrastructure', layout=self.layout)
        store = JobStore(self.layout)
        j = store.get(job.job_id)
        j.assigned_agent = 'vector'
        j.result = 'restart-then-reprobe'
        j.evidence = ['tool_1']
        store.update(j)
        out = learn_from_autonomy_outcome(
            self.layout, job=store.get(job.job_id), success=True,
            method='restart-then-reprobe', peer_verdict='pass',
            evidence_ids=['tool_1'],
        )
        self.assertTrue(out['observations'])

    def test_restart_persistence(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='concise', event_id=f'ev_p_{i}', actor='ledger',
            )
        claim_id = self.eng.store.list_claims(scope='shared')[0].claim_id
        eng2 = LearningEngine(self.layout)
        again = eng2.store.get_claim(claim_id)
        self.assertIsNotNone(again)
        self.assertEqual(again.claim_id, claim_id)

    def test_runtime_context_injection(self):
        for i in range(PATTERN_THRESHOLD):
            ingest_owner_message(
                self.eng, text='brief technical', event_id=f'ev_rt_{i}', actor='ledger',
            )
        ctx = ExpansionRuntime(self.layout).assemble_context('aria', user_message='status')
        self.assertIn('Learned claims', ctx.system_prompt)
        self.assertIn('concise', ctx.system_prompt.lower())
        self.assertIn('learned_claims', ctx.dossier_summary)

    def test_verification_ready_from_rex_not_duplicate(self):
        import expansion.autonomy_loop as al
        import expansion.rex as rex
        self.assertIs(al.verification_ready, rex.verification_ready)
        ok, _ = verification_ready({
            'peer_reviews': [{'reviewer': 'ledger', 'verdict': 'pass'}],
            'owner': 'vector',
            'evidence': ['e1'],
            'research_refs': [],
        })
        self.assertTrue(ok)

    def test_protected_learning_mutations(self):
        self.assertTrue(path_is_protected('/api/expansion/learning/observe'))
        self.assertTrue(path_is_protected('/api/expansion/learning/reinforce'))
        self.assertTrue(path_is_protected('/api/expansion/learning/contradict'))
        self.assertTrue(path_is_protected('/api/expansion/learning/revise'))
        self.assertFalse(path_is_protected('/api/expansion/learning'))
        self.assertFalse(path_is_protected('/api/expansion/learning/why/x'))


if __name__ == '__main__':
    unittest.main()
