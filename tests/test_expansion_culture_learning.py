"""Culture enrichment — seed pack + Aria teaches the roster."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.culture_learning import (
    culture_tick,
    ingest_culture_seed,
    ingest_public_news,
    load_seed_lessons,
)
from expansion.learning import LearningEngine
from expansion.state_layout import resolve_layout


class CultureLearningTests(unittest.TestCase):
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

    def test_seed_pack_ships_lessons(self):
        lessons = load_seed_lessons()
        self.assertGreaterEqual(len(lessons), 8)
        self.assertTrue(any('insult' in (x['text'] or '').lower() for x in lessons))

    def test_bootstrap_ingests_seed_and_teaches_team(self):
        eng = LearningEngine(self.layout)
        shared = eng.store.list_claims(scope='shared', learning_type='social')
        self.assertGreaterEqual(len(shared), 5)
        aria = eng.store.list_claims(
            agent_id='aria', scope='private', learning_type='social',
        )
        self.assertGreaterEqual(len(aria), 5)
        # Roster is taught via shared Keep learning (instant for all agents)
        muse_lines = eng.context_lines('muse', limit=8)
        self.assertTrue(
            any('social' in ln for ln in muse_lines),
            muse_lines,
        )
        lines = eng.context_lines('aria', limit=6)
        self.assertTrue(any('social' in ln for ln in lines))

    def test_seed_idempotent(self):
        again = ingest_culture_seed(self.layout)
        self.assertTrue(again.get('skipped'))
        forced = ingest_culture_seed(self.layout, force=True)
        self.assertFalse(forced.get('skipped'))
        self.assertGreaterEqual(forced.get('lessons') or 0, 8)

    def test_news_distill_offline_mock(self):
        rss = (
            '<?xml version="1.0"?><rss><channel>'
            '<title>BBC News</title>'
            '<item><title>Neighbors rebuild trust after a hard winter storm</title></item>'
            '<item><title>Artists talk about staying kind under pressure</title></item>'
            '</channel></rss>'
        )

        class _Resp:
            def read(self, _n=0):
                return rss.encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch(
            'expansion.culture_learning.urllib.request.urlopen',
            return_value=_Resp(),
        ):
            out = ingest_public_news(self.layout, force=True)
        self.assertTrue(out.get('ok'))
        self.assertFalse(out.get('skipped'))
        self.assertGreaterEqual(len(out.get('headlines') or []), 1)
        eng = LearningEngine(self.layout)
        social = eng.store.list_claims(scope='shared', learning_type='social')
        self.assertTrue(
            any('public media' in (c.claim or '').lower() for c in social)
        )

    def test_culture_tick_wires(self):
        out = culture_tick(self.layout, fetch_news=False)
        self.assertTrue(out.get('ok'))
        self.assertTrue((out.get('seed') or {}).get('ok'))


if __name__ == '__main__':
    unittest.main()
