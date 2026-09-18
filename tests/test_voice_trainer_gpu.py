"""Genome GPU probe must reuse platform WSL nvidia-smi resolver (not bare which)."""
from __future__ import annotations

import unittest
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


if __name__ == '__main__':
    unittest.main()
