"""Full autonomy loop + policy-gated tool execution tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.autonomy_loop import autonomy_tick, process_job, verification_ready
from expansion.bootstrap import bootstrap_runtime_state
from expansion.jobs import JobStore
from expansion.rex import (
    add_peer_review,
    advance_stage,
    close_with_follow_up,
    job_to_card,
    queue_rex_job,
)
from expansion.state_layout import resolve_layout
from expansion.tools import ToolGateway
from expansion.tools.repo import repo_search
from installer.security import path_is_protected


def _fake_web_search(query: str):
    return {
        'query': query,
        'results': [{
            'title': 'Mock research',
            'url': 'https://example.com/doc',
            'snippet': 'Mock autonomous research result for ' + query[:40],
        }],
        'source': 'mock',
    }, 'mock search'


def _fake_web_fetch(url: str):
    return {
        'url': url,
        'content_type': 'text/html',
        'length': 42,
        'snippet': 'Example documentation body for autonomy tests.',
        'title_guess': 'Example',
    }, 'mock fetch'


class AutonomyLoopCase(unittest.TestCase):
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
            'OTACON_WORKSPACE': str(Path(__file__).resolve().parents[1]),
            'OTACON_AUTONOMY_RUN_TESTS': '0',
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)
        self._web = mock.patch.multiple(
            'expansion.tools.web',
            web_search=_fake_web_search,
            web_fetch=_fake_web_fetch,
        )
        self._web.start()

    def tearDown(self):
        self._web.stop()
        self._cm.stop()
        self.tmp.cleanup()

    def test_tool_gateway_policy_and_repo_search(self):
        gw = ToolGateway(self.layout)
        denied = gw.invoke('muse', 'docker.manage', action='ps')
        self.assertFalse(denied.ok)
        self.assertEqual(denied.disposition, 'deny')
        allowed = gw.invoke('vector', 'repo.search', query='autonomy_tick')
        self.assertTrue(allowed.ok)
        self.assertTrue(allowed.data.get('hits') is not None)
        hard = gw.invoke('vector', 'spend_money')
        self.assertFalse(hard.ok)
        self.assertEqual(hard.disposition, 'escalate')

    def test_verification_gate_blocks_blind_close(self):
        job = queue_rex_job('needs verify', domain='infrastructure', layout=self.layout)
        for stage in ('READY', 'ASSIGNED', 'IN_PROGRESS', 'VERIFYING'):
            advance_stage(job.job_id, stage, actor='aria', layout=self.layout)
        with self.assertRaises(ValueError):
            advance_stage(job.job_id, 'DONE', actor='aria', layout=self.layout)

    def test_full_tick_closes_work_with_tools(self):
        job = queue_rex_job(
            'Investigate intermittent Expansion rollback failure',
            domain='infrastructure',
            layout=self.layout,
            priority=2,
        )
        # Drive through multiple ticks until done or rework/hardblock
        final = None
        for _ in range(4):
            out = autonomy_tick(self.layout, max_jobs=3, detect=False)
            self.assertTrue(out['ok'])
            self.assertEqual(out['model'], 'full_autonomy_loop')
            card = job_to_card(JobStore(self.layout).get(job.job_id), self.layout)
            final = card
            if card['stage'] in ('DONE', 'HARD_BLOCKED'):
                break
        self.assertIsNotNone(final)
        self.assertIn(final['stage'], ('DONE', 'VERIFYING', 'REWORK', 'IN_PROGRESS', 'HARD_BLOCKED'))
        # At least research or evidence should exist after ticks
        self.assertTrue(
            final.get('research_refs') or final.get('evidence') or final['stage'] != 'BACKLOG'
        )
        actions = ToolGateway(self.layout).recent(limit=50)
        self.assertTrue(any(a.get('capability') in ('web.search', 'repo.search', 'shell.execute') for a in actions))

    def test_close_with_peer_and_evidence(self):
        job = queue_rex_job('ship fix', domain='infrastructure', layout=self.layout)
        for stage in ('READY', 'ASSIGNED', 'IN_PROGRESS', 'VERIFYING'):
            advance_stage(job.job_id, stage, actor='aria', layout=self.layout)
        store = JobStore(self.layout)
        j = store.get(job.job_id)
        j.evidence = ['tool_evidence_1']
        store.update(j)
        add_peer_review(job.job_id, reviewer='ledger', verdict='pass', note='ok', layout=self.layout)
        out = close_with_follow_up(
            job.job_id, actor='aria', result='shipped',
            follow_up_request='Document outcome',
            follow_up_domain='records', layout=self.layout,
        )
        self.assertEqual(out['job'].status, 'COMPLETE')
        self.assertIsNotNone(out['follow_up'])

    def test_protected_tick_and_tools(self):
        self.assertTrue(path_is_protected('/api/expansion/rex/tick'))
        self.assertTrue(path_is_protected('/api/expansion/tools/invoke'))


if __name__ == '__main__':
    unittest.main()
