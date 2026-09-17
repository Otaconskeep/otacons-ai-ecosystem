"""Unit tests for installer security helpers and readiness honesty."""
import os
import unittest
from pathlib import Path

from installer.security import (
    is_loopback_host,
    path_is_protected,
    resolve_bind_host,
    safe_config_root,
    safe_ui_path,
)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        for k in list(os.environ):
            if k.startswith('OTACON_'):
                del os.environ[k]

    def test_default_local_bind(self):
        host, mode = resolve_bind_host()
        self.assertEqual(mode, 'local')
        self.assertEqual(host, '127.0.0.1')

    def test_lan_opt_in(self):
        os.environ['OTACON_LAN_MODE'] = '1'
        host, mode = resolve_bind_host()
        self.assertEqual(mode, 'lan')
        self.assertEqual(host, '0.0.0.0')

    def test_lan_disabled_overrides_host(self):
        os.environ['OTACON_LAN_MODE'] = '0'
        os.environ['OTACON_HOST'] = '0.0.0.0'
        host, mode = resolve_bind_host()
        self.assertEqual(mode, 'local')
        # Bind-all is allowed in local auth mode (WSL reachability).
        self.assertEqual(host, '0.0.0.0')

    def test_bind_all_without_lan_flag_is_local(self):
        os.environ['OTACON_HOST'] = '0.0.0.0'
        host, mode = resolve_bind_host()
        self.assertEqual(mode, 'local')
        self.assertEqual(host, '0.0.0.0')

    def test_ui_path_traversal_rejected(self):
        ui = Path(__file__).resolve().parent.parent / 'ui'
        self.assertIsNotNone(safe_ui_path(ui, '/index.html'))
        self.assertIsNone(safe_ui_path(ui, '/../installer/server.py'))
        self.assertIsNone(safe_ui_path(ui, '/foo/../../etc/passwd'))

    def test_config_root_confined(self):
        with self.assertRaises(ValueError):
            safe_config_root('/tmp/not-allowed')
        root = safe_config_root(None)
        self.assertTrue(str(root).endswith('otacon') or 'otacon' in str(root))

    def test_protected_paths(self):
        self.assertTrue(path_is_protected('/api/chat_with_agent'))
        self.assertTrue(path_is_protected('/api/save'))
        self.assertFalse(path_is_protected('/api/branding'))
        self.assertFalse(path_is_protected('/api/capabilities'))

    def test_loopback(self):
        self.assertTrue(is_loopback_host('127.0.0.1'))
        self.assertFalse(is_loopback_host('0.0.0.0'))


if __name__ == '__main__':
    unittest.main()
