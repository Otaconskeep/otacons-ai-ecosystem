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


if __name__ == '__main__':
    unittest.main()
