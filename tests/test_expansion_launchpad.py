"""Command Center launchpad + companion auto-tiles."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.launchpad import build_launchpad, save_prefs
from expansion.state_layout import resolve_layout


class LaunchpadCase(unittest.TestCase):
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

    def test_launchpad_has_homescreen_tabs_and_companions(self):
        lp = build_launchpad(self.layout)
        tab_ids = {t['id'] for t in lp['tabs']}
        self.assertIn('homescreen', tab_ids)
        self.assertIn('codec', tab_ids)
        ids = {t['id'] for t in lp['tiles']}
        self.assertIn('codec', ids)
        self.assertIn('keep_desk', ids)
        self.assertIn('keeproute', ids)

    def test_configured_keeproute_becomes_available_tile(self):
        save_prefs({'keeproute_url': 'http://127.0.0.1:20129/'}, self.layout)
        lp = build_launchpad(self.layout)
        kr = next(t for t in lp['tiles'] if t['id'] == 'keeproute')
        self.assertTrue(kr['available'])
        self.assertEqual(kr['href'], 'http://127.0.0.1:20129/')
        tab_ids = {t['id'] for t in lp['tabs']}
        self.assertIn('keeproute', tab_ids)


if __name__ == '__main__':
    unittest.main()
