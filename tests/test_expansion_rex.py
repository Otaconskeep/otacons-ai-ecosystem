"""Project REX — autonomous work substrate + policy engine tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.jobs import JobStore
from expansion.policy import HARD_BOUNDARIES, PolicyEngine
from expansion.rex import (
    HARD_BLOCK_STAGE,
    REX_STAGES,
    add_peer_review,
    advance_stage,
    build_autonomy_dashboard,
    build_rex_board,
    close_with_follow_up,
    discover_work,
    job_to_card,
    queue_rex_job,
    set_coordination_plan,
    transition_rex_job,
)
from expansion.rooms import RoomRegistry
from expansion.state_layout import resolve_layout
from installer.security import path_is_protected


class RexAutonomyCase(unittest.TestCase):
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

    def test_room_registry_includes_project_rex(self):
        rooms = RoomRegistry(self.layout).seed_defaults()
        self.assertIn('project_rex', {r.page_id for r in rooms})

    def test_board_uses_autonomous_stages_not_approval(self):
        job = discover_work(
            'sentry', 'Codec latency +42%', domain='security', layout=self.layout,
        )
        advance_stage(job.job_id, 'READY', actor='aria', layout=self.layout)
        advance_stage(job.job_id, 'RESEARCHING', actor='vector', layout=self.layout)
        set_coordination_plan(job.job_id, [
            'Assign Vector investigation',
            'Allow Vector web R&D',
            'Ledger collects evidence',
            'Vector patches',
            'Run regression suite',
            'Sentry verifies no security regression',
            'If green, merge/close',
            'Journal outcome',
        ], actor='aria', layout=self.layout)

        board = build_rex_board(self.layout)
        self.assertEqual(board['model'], 'autonomous_work_system')
        self.assertFalse(any(
            'approval' in (c.get('label') or '').lower()
            for c in board['columns']
        ))
        stages = [c['stage'] for c in board['columns'] if not c.get('oversight_only')]
        self.assertEqual(stages, [s for s, _ in REX_STAGES])
        self.assertIn('discover', board['loop'])
        blob = str(board).lower()
        self.assertNotIn('xof', blob)
        self.assertNotIn('awaiting user approval', blob)
        self.assertNotIn('/opt/otacon', blob)

        card = next(
            c for col in board['columns'] for c in col['cards']
            if c['job_id'] == job.job_id
        )
        self.assertEqual(card['stage'], 'RESEARCHING')
        self.assertFalse(card['awaiting_user_approval'])
        self.assertEqual(len(card['coordination_plan']), 8)

    def test_policy_authorizes_domain_denies_hard_boundaries(self):
        eng = PolicyEngine(self.layout)
        ok = eng.check('vector', 'web.search')
        self.assertTrue(ok.allowed)
        self.assertEqual(ok.disposition, 'authorize')
        deny = eng.check('vector', 'spend_money')
        self.assertFalse(deny.allowed)
        self.assertEqual(deny.disposition, 'escalate')
        for cap in HARD_BOUNDARIES:
            self.assertEqual(eng.check('aria', cap).disposition, 'escalate')
        with self.assertRaises(PermissionError):
            eng.require('muse', 'docker.manage')

    def test_agent_loop_verify_rework_retry_budget(self):
        job = queue_rex_job('flaky patch', domain='infrastructure', layout=self.layout)
        advance_stage(job.job_id, 'READY', actor='aria', layout=self.layout)
        advance_stage(
            job.job_id, 'ASSIGNED', actor='aria', layout=self.layout, assign_to='vector',
        )
        advance_stage(job.job_id, 'IN_PROGRESS', actor='vector', layout=self.layout)
        advance_stage(job.job_id, 'VERIFYING', actor='vector', layout=self.layout)
        add_peer_review(
            job.job_id, reviewer='ledger', verdict='fail',
            note='missing evidence', layout=self.layout,
        )
        advance_stage(
            job.job_id, 'REWORK', actor='ledger', layout=self.layout, note='verify failed',
        )
        for _ in range(2):
            advance_stage(job.job_id, 'IN_PROGRESS', actor='vector', layout=self.layout)
            advance_stage(job.job_id, 'VERIFYING', actor='vector', layout=self.layout)
            advance_stage(job.job_id, 'REWORK', actor='sentry', layout=self.layout)

        store = JobStore(self.layout)
        card = job_to_card(store.get(job.job_id), self.layout)
        self.assertEqual(card['stage'], HARD_BLOCK_STAGE)
        dash = build_autonomy_dashboard(self.layout)
        self.assertEqual(dash['model'], 'observe_not_approve')
        self.assertGreaterEqual(dash['metrics']['hard_blockers'], 1)

    def test_close_creates_follow_up(self):
        job = queue_rex_job('ship fix', domain='infrastructure', layout=self.layout)
        for stage in ('READY', 'ASSIGNED', 'IN_PROGRESS', 'VERIFYING'):
            advance_stage(job.job_id, stage, actor='aria', layout=self.layout)
        store = JobStore(self.layout)
        j = store.get(job.job_id)
        j.evidence = ['ev_1']
        store.update(j)
        add_peer_review(job.job_id, reviewer='ledger', verdict='pass', note='ok', layout=self.layout)
        out = close_with_follow_up(
            job.job_id, actor='aria', result='shipped',
            follow_up_request='Document regression in Ledger',
            follow_up_domain='records', layout=self.layout,
        )
        self.assertEqual(out['job'].status, 'COMPLETE')
        self.assertIsNotNone(out['follow_up'])
        follow_card = job_to_card(out['follow_up'], self.layout)
        self.assertEqual(follow_card['stage'], 'BACKLOG')
        self.assertEqual(follow_card['follow_up_of'], job.job_id)
        parent = job_to_card(JobStore(self.layout).get(job.job_id), self.layout)
        self.assertIn(follow_card['job_id'], parent['follow_ups'])

    def test_legacy_transition_maps_to_stages(self):
        job = queue_rex_job('legacy2', domain='coordination', layout=self.layout)
        advance_stage(job.job_id, 'READY', actor='aria', layout=self.layout)
        advance_stage(job.job_id, 'ASSIGNED', actor='aria', layout=self.layout)
        moved = transition_rex_job(job.job_id, 'RUNNING', actor='vector', layout=self.layout)
        card = job_to_card(moved, self.layout)
        self.assertEqual(card['stage'], 'IN_PROGRESS')

    def test_protected_rex_mutations(self):
        self.assertTrue(path_is_protected('/api/expansion/rex/transition'))
        self.assertTrue(path_is_protected('/api/expansion/rex/discover'))
        self.assertTrue(path_is_protected('/api/expansion/rex/peer-review'))
        self.assertTrue(path_is_protected('/api/expansion/policy/check'))
        self.assertFalse(path_is_protected('/api/expansion/rex'))
        self.assertFalse(path_is_protected('/api/expansion/rex/autonomy'))


if __name__ == '__main__':
    unittest.main()
