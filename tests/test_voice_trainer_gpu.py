"""Genome GPU probe must reuse platform WSL nvidia-smi resolver (not bare which)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.capabilities import voice_trainer as vt


class TestVoiceTrainerGpu(unittest.TestCase):
    def test_gpu_usable_uses_resolved_smi_and_env(self):
        with mock.patch('core.platform._resolve_nvidia_smi', return_value='/usr/lib/wsl/lib/nvidia-smi'):
            with mock.patch('core.platform._nvidia_smi_env', return_value={'PATH': '/usr/lib/wsl/lib'}):
                with mock.patch('subprocess.run') as run:
                    run.return_value = mock.Mock(returncode=0)
                    self.assertTrue(vt._gpu_usable())
        self.assertEqual(run.call_args.args[0][0], '/usr/lib/wsl/lib/nvidia-smi')
        self.assertEqual(run.call_args.kwargs.get('env', {}).get('PATH'), '/usr/lib/wsl/lib')

    def test_gpu_usable_false_when_smi_missing(self):
        with mock.patch('core.platform._resolve_nvidia_smi', return_value=None):
            self.assertFalse(vt._gpu_usable())

    def test_install_refuses_without_gpu(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / 'nope'
            with mock.patch.object(vt, '_vt_home', return_value=missing):
                with mock.patch.object(vt, '_gpu_usable', return_value=False):
                    out = vt.install_voice_trainer()
        self.assertFalse(out['ok'])
        self.assertEqual(out['action'], 'no_gpu')

    def test_install_already_installed(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / 'marker.txt').write_text('x', encoding='utf-8')
            with mock.patch.object(vt, '_vt_home', return_value=home):
                with mock.patch.object(vt, 'ensure_voice_trainer_ui', return_value={'url': 'http://127.0.0.1:8765/'}):
                    out = vt.install_voice_trainer()
        self.assertTrue(out['ok'])
        self.assertEqual(out['action'], 'already_installed')

    def test_genome_install_command_uses_wsl_root_when_unprivileged(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            with mock.patch.object(vt, '_wsl_exe', return_value='/mnt/c/Windows/System32/wsl.exe'):
                with mock.patch('os.geteuid', return_value=1000):
                    with mock.patch('subprocess.run', return_value=mock.Mock(returncode=1)):
                        cmd, err = vt._genome_install_command(home, {'USER': 'crist'})
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd[0], '/mnt/c/Windows/System32/wsl.exe')
        self.assertIn('-u', cmd)
        self.assertIn('root', cmd)
        self.assertNotIn('-lc', cmd)  # never unquoted -lc with Windows PATH
        self.assertEqual(cmd[-2:], ['bash', str(vt._GENOME_INSTALL_SCRIPT)])
        self.assertFalse(err)
        script = vt._GENOME_INSTALL_SCRIPT.read_text(encoding='utf-8')
        self.assertIn('PATH=/usr/lib/wsl/lib:', script)
        self.assertNotIn('$PATH', script)
        self.assertNotIn('(x86)', script)

    def test_genome_install_needs_root_without_wsl_or_sudo(self):
        home = Path(tempfile.mkdtemp()) / 'missing'
        with mock.patch.object(vt, '_vt_home', return_value=home):
            with mock.patch.object(vt, '_gpu_usable', return_value=True):
                with mock.patch.object(vt, '_wsl_exe', return_value=None):
                    with mock.patch('os.geteuid', return_value=1000):
                        with mock.patch('subprocess.run', return_value=mock.Mock(returncode=1)):
                            # Clear install marker from prior tests
                            if vt._INSTALL_MARKER.is_file():
                                vt._INSTALL_MARKER.unlink()
                            out = vt.install_voice_trainer()
        self.assertFalse(out['ok'])
        self.assertEqual(out['action'], 'needs_root')
        self.assertIn('wsl', (out.get('hint') or '').lower())


if __name__ == '__main__':
    unittest.main()
