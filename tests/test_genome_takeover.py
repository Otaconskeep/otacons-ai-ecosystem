"""Genome UI must replace classic Voice Trainer status http.server on :8765."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from expansion.capabilities import genome_ui as gui
from expansion.capabilities import voice_trainer_status as vts


class _ClassicStatusHandler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        return

    def do_GET(self):  # noqa: N802
        body = b'Voice Trainer ready.\n'
        if self.path.startswith('/status.json'):
            body = json.dumps({'ok': True, 'gpu': True}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json' if self.path.endswith('.json') else 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GenomeTakeoverTests(unittest.TestCase):
    def tearDown(self):
        srv = gui._SERVER
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        gui._SERVER = None
        gui._SERVER_THREAD = None

    def test_reclaim_classic_status_then_genome_api(self):
        with TemporaryDirectory() as td:
            home = Path(td)
            ui = home / 'ui'
            ui.mkdir()
            (ui / 'index.html').write_text('<html>Voice Trainer ready.</html>', encoding='utf-8')
            classic = ThreadingHTTPServer(('127.0.0.1', 0), _ClassicStatusHandler)
            port = classic.server_address[1]
            th = threading.Thread(target=classic.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
            th.start()
            # Pretend classic is Otacon-owned VT ui server
            (ui / vts.PID_NAME).write_text(str(classic.server_address), encoding='utf-8')
            # PID file should be the process pid — use real server thread isn't the listen pid.
            # Start a real http.server child so reclaim can SIGTERM it via cwd match.
            classic.shutdown()
            classic.server_close()

            # Launch real python http.server as classic VT would
            import os
            import subprocess
            import time
            log = open(os.devnull, 'wb')
            proc = subprocess.Popen(
                ['python3', '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                cwd=str(ui),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            (ui / vts.PID_NAME).write_text(str(proc.pid) + '\n', encoding='utf-8')
            time.sleep(0.4)
            self.assertTrue(vts.port_listening(port))
            self.assertFalse(gui._genome_api_live(port))

            with mock.patch.object(gui, '_vt_home', return_value=home), \
                 mock.patch.object(vts, 'resolve_install_dir', return_value=home), \
                 mock.patch.object(vts, 'write_status_json', return_value={'path': str(ui / 'status.json'), 'status': {'ok': True}}):
                out = gui.ensure_genome_ui(port=port)

            self.assertTrue(out.get('ok'), out)
            self.assertTrue(gui._genome_api_live(port), out)
            self.assertIn(out.get('action'), ('reclaimed_classic', 'started', 'port_freed', 'already_listening'))
            # cleanup genome server
            if gui._SERVER:
                gui._SERVER.shutdown()
                gui._SERVER.server_close()
            gui._SERVER = None
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()


if __name__ == '__main__':
    unittest.main()
