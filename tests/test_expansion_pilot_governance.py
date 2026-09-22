"""Controlled-pilot governance clean-room tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.pilot_governance import (
    HARD_BLOCKED_DOMAINS,
    PILOT_ALLOWED_DOMAINS,
    auto_rollback_job,
    bootstrap_pilot,
    definition_of_done,
    dispatch_gate,
    enable_controlled_pilot,
    load_status,
    record_pilot_close,
    save_status,
)
from expansion.state_layout import resolve_layout


class PilotGovernanceCase(unittest.TestCase):
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
        enable_controlled_pilot(self.layout, graduation_min=3)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def test_allowlist_dispatch(self):
        ok = dispatch_gate(domain='learning', stage='IN_PROGRESS', layout=self.layout)
        self.assertTrue(ok['allow'])
        self.assertEqual(ok['kind'], 'pilot_allowlisted_domain')
        blocked = dispatch_gate(domain='infrastructure', stage='IN_PROGRESS', layout=self.layout)
        self.assertFalse(blocked['allow'])
        self.assertEqual(blocked['kind'], 'production_gated')
        denied = dispatch_gate(domain='unknown_xyz', stage='IN_PROGRESS', layout=self.layout)
        self.assertFalse(denied['allow'])

    def test_dod_requires_before_after_in_pilot(self):
        weak = definition_of_done(
            domain='learning',
            evidence=['py_compile ok'],
            result='compileall',
            peer_reviews=[{'verdict': 'pass'}],
            layout=self.layout,
        )
        self.assertFalse(weak['passed'])
        self.assertIn('before_after_evidence', weak['missing'])

        good = definition_of_done(
            domain='learning',
            evidence=['before:x', 'after:y', 'pytest passed'],
            result='acceptance suite green',
            peer_reviews=[{'verdict': 'pass'}],
            implementation_evidence={'before_metric': 1, 'after_metric': 3},
            layout=self.layout,
        )
        self.assertTrue(good['passed'], good)
        self.assertGreater(good.get('derived_confidence') or 0, 0)

    def test_dod_blocks_journal_only_research_close(self):
        """repo.search + before/after bookkeeping must not pass research DoD."""
        fake = definition_of_done(
            domain='continuity',
            evidence=[
                'tool_24942d4d87',
                'before:evidence=0',
                'after:actions=1:ok=1',
            ],
            result='Executed 1 tool action(s); ok=1 fail=0',
            peer_reviews=[{'verdict': 'pass', 'reviewer': 'ledger'}],
            research_refs=[],
            implementation_evidence={
                'before_metric': 0,
                'after_metric': 1,
                'before_state': {'evidence_count': 0},
                'after_state': {'actions': 1, 'ok_actions': 1},
            },
            layout=self.layout,
        )
        self.assertFalse(fake['passed'], fake)
        self.assertTrue(
            set(fake['missing']) & {'research_outcome', 'outcome_delta'},
            fake['missing'],
        )

        bookkeeping_only = definition_of_done(
            domain='learning',
            evidence=['before:evidence=0', 'after:actions=1:ok=1'],
            result='Executed 1 tool action(s)',
            peer_reviews=[{'verdict': 'pass'}],
            implementation_evidence={'before_metric': 0, 'after_metric': 1},
            layout=self.layout,
        )
        self.assertFalse(bookkeeping_only['passed'])
        self.assertIn('has_evidence', bookkeeping_only['missing'])


    def test_graduation_streak_and_reset(self):
        record_pilot_close(job_id='j1', clean=True, layout=self.layout)
        record_pilot_close(job_id='j2', clean=True, layout=self.layout)
        st = load_status(self.layout)
        self.assertEqual(st['pilot_consecutive_clean_closes'], 2)
        self.assertFalse(st['pilot_graduated'])
        record_pilot_close(job_id='j3', clean=False, reason='rollback', layout=self.layout)
        st = load_status(self.layout)
        self.assertEqual(st['pilot_consecutive_clean_closes'], 0)
        record_pilot_close(job_id='j4', clean=True, layout=self.layout)
        record_pilot_close(job_id='j5', clean=True, layout=self.layout)
        record_pilot_close(job_id='j6', clean=True, layout=self.layout)
        st = load_status(self.layout)
        self.assertTrue(st['pilot_graduated'])
        self.assertEqual(st['pilot_consecutive_clean_closes'], 3)

    def test_bootstrap_preserves_pilot(self):
        save_status({
            'active': True,
            'mode': 'controlled_pilot',
            'freeze_new_proposals': False,
            'soak_dispatch_halted': False,
            'pilot_consecutive_clean_closes': 2,
        }, self.layout)
        st = bootstrap_pilot(self.layout)
        self.assertEqual(st['mode'], 'controlled_pilot')
        self.assertFalse(st['freeze_new_proposals'])
        self.assertEqual(st['pilot_consecutive_clean_closes'], 2)

    def test_sets_are_disjoint(self):
        self.assertFalse(PILOT_ALLOWED_DOMAINS & HARD_BLOCKED_DOMAINS)


if __name__ == '__main__':
    unittest.main()
