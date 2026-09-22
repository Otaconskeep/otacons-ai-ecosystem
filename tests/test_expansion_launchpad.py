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

    def test_scheme_less_prefs_do_not_mask_discovery(self):
        """Junk like 127.0.0.1:98 must not block port discovery forever."""
        from expansion.launchpad import _normalize_companion_url, _resolve_companion, _COMPANION_DEFAULTS
        self.assertEqual(_normalize_companion_url('127.0.0.1:98'), '')
        self.assertEqual(_normalize_companion_url('http://127.0.0.1:20129/'), 'http://127.0.0.1:20129/')
        save_prefs({
            'keeproute_url': '127.0.0.1:98',
            'keep_desk_url': '127.0.0.1:99',
        }, self.layout)
        prefs = __import__('expansion.launchpad', fromlist=['load_prefs']).load_prefs(self.layout)
        self.assertNotIn('keeproute_url', prefs)
        self.assertNotIn('keep_desk_url', prefs)
        with mock.patch('expansion.launchpad._tcp_open', side_effect=lambda h, p, timeout=0.35: p == 20129):
            kr_spec = next(s for s in _COMPANION_DEFAULTS if s['id'] == 'keeproute')
            tile = _resolve_companion(kr_spec, {'keeproute_url': '127.0.0.1:98'})
        self.assertTrue(tile['live'])
        self.assertEqual(tile['source'], 'discovered')
        self.assertEqual(tile['href'], 'http://127.0.0.1:20129/')

    def test_keep_desk_reports_unshipped(self):
        lp = build_launchpad(self.layout)
        desk = next(t for t in lp['tiles'] if t['id'] == 'keep_desk')
        self.assertFalse(desk.get('shipped', True))
        self.assertEqual(desk['source'], 'missing')
        self.assertIn('Not shipped', desk['hint'])


if __name__ == '__main__':
    unittest.main()
