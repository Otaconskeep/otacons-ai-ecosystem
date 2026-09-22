"""KeepRoute / OmniRoute → world model → REX proposal feed (Premium Expansion)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.autonomy_loop import _detect_world_model_work
from expansion.bootstrap import bootstrap_runtime_state
from expansion.jobs import JobStore
from expansion.rex import job_to_card
from expansion.route_learning import (
    ingest_keeproute_exchange,
    pool_summary,
    recommend,
    record_resolution,
)
from expansion.state_layout import resolve_layout
from expansion.world_model import get_world_model, invalidate_world_model


class RouteLearningRexCase(unittest.TestCase):
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
        invalidate_world_model()

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def test_ingest_writes_global_pool(self):
        out = ingest_keeproute_exchange(
            prompt='Fix docker host.docker.internal DNS for OmniRoute CLI',
            response='Validated. Pointed at gateway IP.',
            agent='ollama',
            model='ollama-local/llama3',
            source='keeproute-omniroute',
            success=True,
            layout=self.layout,
        )
        self.assertTrue(out.get('ok'))
        self.assertFalse(out.get('skipped'))
        summary = pool_summary(self.layout)
        self.assertEqual(summary['records'], 1)
        self.assertTrue(summary['global_pool'])
        self.assertGreaterEqual(summary['traces'], 1)

    def test_failures_become_world_model_risks(self):
        for i in range(3):
            ingest_keeproute_exchange(
                prompt=f'VALIDATE_CLI_OK probe attempt {i} with host.docker.internal',
                response='',
                agent='ollama-local',
                source='keeproute',
                success=False,
                error='connection refused host.docker.internal',
                layout=self.layout,
            )
        invalidate_world_model()
        wm = get_world_model(self.layout)
        risks = wm.get_active_risks()
        self.assertTrue(risks, 'expected risks from failed exchanges')
        domains = {r.get('domain') for r in risks}
        self.assertTrue('keeproute' in domains or any(
            'keeproute' in (r.get('entity') or '') or 'Operation failure' in (r.get('description') or '')
            for r in risks
        ))

    def test_recommend_is_global_not_siloed(self):
        record_resolution(
            problem='[keeproute/codex] DNS resolution failed for internal gateway',
            action_taken='Routed via keeproute → codex',
            result='Fixed /etc/hosts mapping',
            success=True,
            domain='keeproute',
            tags=['keeproute', 'codex'],
            layout=self.layout,
        )
        hits = recommend('gateway DNS broken on my workstation', layout=self.layout)
        self.assertTrue(hits, 'unrelated wording should still surface matching records')

    def test_world_model_spawns_rex_with_source_tag(self):
        for i in range(4):
            ingest_keeproute_exchange(
                prompt=f'low confidence routing flake {i} VALIDATE_CLI_OK',
                response='partial',
                agent='ollama-local',
                success=False,
                error='timeout',
                layout=self.layout,
            )
        invalidate_world_model()
        created = _detect_world_model_work(self.layout)
        self.assertTrue(created, 'world_model risks should create REX jobs')
        store = JobStore(self.layout)
        job = store.get(created[0])
        card = job_to_card(job, self.layout)
        self.assertTrue(
            str(card.get('proposal_source') or '').startswith('world_model:'),
            card.get('proposal_source'),
        )


if __name__ == '__main__':
    unittest.main()
