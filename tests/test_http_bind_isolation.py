"""Installer docs + HTTP test isolation contracts (self-check flake guards)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.http_server_isolation import force_local_bind, restore_server_bind, snapshot_server_bind


class InstallerPipeEnvDocsTests(unittest.TestCase):
    def test_readme_puts_install_env_on_bash_not_curl(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        # Bad: OTACON_*=… curl … | bash  (env only applies to curl)
        bad = re.search(
            r'OTACON_INSTALL_[A-Z0-9_]+=\S+\s+curl\s+-fsSL[^\n]*\|\s*bash',
            readme,
        )
        self.assertIsNone(
            bad,
            'README must not put OTACON_INSTALL_* before curl in a curl|bash pipe'
            + (f' (matched: {bad.group(0)!r})' if bad else ''),
        )
        self.assertIn('| OTACON_INSTALL_DEFAULT_MODEL=0 OTACON_INSTALL_VOICE_TRAINER=0 bash', readme)


class HttpBindIsolationTests(unittest.TestCase):
    def test_force_local_bind_roundtrip(self):
        from installer import server as srv
        snap = snapshot_server_bind(srv)
        try:
            srv.BIND_MODE = 'lan'
            srv.LAN_TOKEN = 'pollution-token'
            forced = force_local_bind(srv)
            self.assertEqual(srv.BIND_MODE, 'local')
            self.assertIsNone(srv.LAN_TOKEN)
            restore_server_bind(srv, forced)
            self.assertEqual(srv.BIND_MODE, 'lan')
            self.assertEqual(srv.LAN_TOKEN, 'pollution-token')
        finally:
            restore_server_bind(srv, snap)


if __name__ == '__main__':
    unittest.main()
