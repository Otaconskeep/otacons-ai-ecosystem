"""Expansion Voice Trainer status.json write/repair regressions (A–F subset)."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from expansion.capabilities import voice_trainer_status as vts


class ExpansionVoiceTrainerStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'otacon-voice-trainer'
        self.ui = self.home / 'ui'
        self.ui.mkdir(parents=True)
        (self.ui / 'index.html').write_text('<html>vt</html>', encoding='utf-8')

    def tearDown(self):
        pid_path = self.ui / vts.PID_NAME
        if pid_path.is_file():
            try:
                os.kill(int(pid_path.read_text().strip()), 15)
            except (OSError, ValueError):
                pass
        self.tmp.cleanup()

    def _port(self) -> int:
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        p = s.getsockname()[1]
        s.close()
        return p

    def test_resolve_dir_uses_env_not_crist(self):
        with mock.patch.dict(os.environ, {'OTACON_VT_DIR': str(self.home), 'HOME': '/home/crist'}):
            d = vts.resolve_install_dir()
        self.assertEqual(d, self.home.resolve())
        self.assertNotIn('/home/crist/otacon-voice-trainer', str(d))

    def test_resolve_dir_block_home(self):
        block = Path(self.tmp.name) / 'home' / 'block'
        block.mkdir(parents=True)
        with mock.patch.dict(os.environ, {'HOME': str(block)}, clear=False):
            os.environ.pop('OTACON_VT_DIR', None)
            d = vts.resolve_install_dir()
        self.assertEqual(d, (block / 'otacon-voice-trainer').resolve())

    def test_A_gpu_status_written(self):
        with mock.patch.object(vts, 'probe_gpu', return_value={
            'gpu_state': 'gpu_detected', 'gpu_name': 'TestGPU', 'gpu_vram_mb': 6144,
            'gpu_probe_error': None,
        }), mock.patch.object(vts, 'detect_image', return_value='piper-voice-trainer:gpu'):
            out = vts.write_status_json(self.home)
        st = out['status']
        self.assertEqual(st['gpu_name'], 'TestGPU')
        self.assertEqual(st['gpu_vram_mb'], 6144)
        self.assertEqual(st['install_dir'], str(self.home.resolve()))
        self.assertTrue((self.ui / 'status.json').is_file())

    def test_B_cpu_only_nulls(self):
        with mock.patch.object(vts, 'probe_gpu', return_value={
            'gpu_state': 'cpu_only', 'gpu_name': None, 'gpu_vram_mb': None,
            'gpu_probe_error': None,
        }), mock.patch.object(vts, 'detect_image', return_value=None):
            st = vts.write_status_json(self.home)['status']
        self.assertIsNone(st['gpu_name'])
        self.assertIsNone(st['gpu_vram_mb'])

    def test_C_repair_missing_status(self):
        port = self._port()
        proc = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
            cwd=str(self.ui),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        (self.ui / vts.PID_NAME).write_text(str(proc.pid) + '\n', encoding='utf-8')
        time.sleep(0.4)
        with mock.patch.object(vts, 'probe_gpu', return_value={
            'gpu_state': 'gpu_detected', 'gpu_name': 'G', 'gpu_vram_mb': 1,
            'gpu_probe_error': None,
        }), mock.patch.object(vts, 'detect_image', return_value='piper-voice-trainer:gpu'):
            result = vts.ensure_status_and_ui(
                install_dir=self.home, port=port, prefer_genome_ui=False,
            )
        self.assertTrue(result['ok'], result)
        self.assertTrue((self.ui / 'status.json').is_file())
        try:
            os.kill(proc.pid, 15)
        except OSError:
            pass

    def test_E_foreign_port_conflict(self):
        port = self._port()
        foreign = Path(self.tmp.name) / 'foreign'
        foreign.mkdir()
        (foreign / 'index.html').write_text('x', encoding='utf-8')
        proc = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
            cwd=str(foreign),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(0.4)
        with mock.patch.object(vts, 'probe_gpu', return_value={
            'gpu_state': 'cpu_only', 'gpu_name': None, 'gpu_vram_mb': None,
            'gpu_probe_error': None,
        }), mock.patch.object(vts, 'detect_image', return_value=None):
            result = vts.ensure_status_and_ui(
                install_dir=self.home, port=port, prefer_genome_ui=False,
            )
        self.assertFalse(result['ok'])
        self.assertEqual(result['action'], 'port_conflict')
        self.assertIsNone(proc.poll())
        try:
            os.kill(proc.pid, 15)
        except OSError:
            pass

    def test_docs_env_not_on_curl(self):
        bad = 'OTACON_INSTALL_VOICE_TRAINER=1 curl'
        readme = Path(__file__).resolve().parents[1] / 'README.md'
        # Ecosystem README uses correct pipe form for skip; voice-trainer docs fixed upstream.
        # Guard Expansion wizard / site snippets that might still embed the bad pattern.
        wizard = Path(__file__).resolve().parents[1] / 'ui' / 'wizard.js'
        text = wizard.read_text(encoding='utf-8')
        self.assertNotIn(bad, text)


if __name__ == '__main__':
    unittest.main()
