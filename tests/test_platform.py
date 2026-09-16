"""GPU detection must work when systemd strips PATH (WSL nvidia-smi case)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from core.platform import (
    _nvidia_smi_env,
    _resolve_nvidia_smi,
    detect,
)


class PlatformGpuTests(unittest.TestCase):
    def test_wsl_lib_on_ld_and_path(self):
        env = _nvidia_smi_env()
        self.assertIn('/usr/lib/wsl/lib', env.get('PATH', ''))
        # LD only required when the directory exists on this host
        if os.path.isdir('/usr/lib/wsl/lib'):
            self.assertIn('/usr/lib/wsl/lib', env.get('LD_LIBRARY_PATH', ''))

    def test_resolve_prefers_absolute_when_which_empty(self):
        with mock.patch('core.platform.shutil.which', return_value=None):
            with mock.patch('core.platform.os.path.isfile', side_effect=lambda p: p == '/usr/bin/nvidia-smi'):
                with mock.patch('core.platform.os.access', return_value=True):
                    self.assertEqual(_resolve_nvidia_smi(), '/usr/bin/nvidia-smi')

    def test_detect_uses_resolved_smi_not_bare_name(self):
        fake = 'FAKEGPU, 8192\n'
        with mock.patch('core.platform._resolve_nvidia_smi', return_value='/usr/bin/nvidia-smi'):
            with mock.patch('core.platform.subprocess.check_output', return_value=fake) as co:
                h = detect()
        self.assertEqual(co.call_args.args[0][0], '/usr/bin/nvidia-smi')
        self.assertTrue(h.gpus)
        self.assertEqual(h.gpus[0].model, 'FAKEGPU')
        self.assertEqual(h.gpu_detection['status'], 'detected')
        self.assertIn('Detected', h.gpu_detection['message'])

    def test_detect_empty_output_is_none_not_detected(self):
        with mock.patch('core.platform._resolve_nvidia_smi', return_value='/usr/bin/nvidia-smi'):
            with mock.patch('core.platform.subprocess.check_output', return_value='\n'):
                h = detect()
        self.assertEqual(h.gpus, [])
        self.assertEqual(h.gpu_detection['status'], 'none')


if __name__ == '__main__':
    unittest.main()
