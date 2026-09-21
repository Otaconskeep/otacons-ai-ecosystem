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
            with mock.patch('core.platform._nvidia_smi_query', return_value='\n'):
                with mock.patch('core.platform._proc_nvidia_gpus', return_value=[]):
                    h = detect()
        self.assertEqual(h.gpus, [])
        self.assertEqual(h.gpu_detection['status'], 'none')

    def test_resolve_docker_falls_back_to_absolute(self):
        from core.platform import _resolve_docker
        with mock.patch('core.platform.shutil.which', return_value=None):
            with mock.patch(
                'core.platform.os.path.isfile',
                side_effect=lambda p: p == '/usr/bin/docker',
            ):
                with mock.patch('core.platform.os.access', return_value=True):
                    self.assertEqual(_resolve_docker(), '/usr/bin/docker')

    def test_tool_env_includes_docker_desktop_path(self):
        from core.platform import docker_env
        env = docker_env()
        self.assertIn('Docker/resources/bin', env.get('PATH', ''))

    def test_detect_proc_fallback_enriches_4090_vram(self):
        from core.platform import GPU

        proc = [GPU('gpu_001', 'nvidia', 'NVIDIA GeForce RTX 4090', 0.0, 'GPU_SMALL')]
        with mock.patch('core.platform._resolve_nvidia_smi', return_value=None):
            with mock.patch('core.platform._proc_nvidia_gpus', return_value=proc):
                h = detect()
        self.assertEqual(len(h.gpus), 1)
        self.assertEqual(h.gpus[0].vram_gb, 24.0)
        self.assertEqual(h.gpus[0].capability, 'GPU_HIGH_END')
        self.assertEqual(h.gpu_detection['status'], 'detected')
        self.assertIn('SKU', h.gpu_detection['message'])

    def test_detect_uses_windows_gpu_hint_env(self):
        with mock.patch('core.platform._resolve_nvidia_smi', return_value=None):
            with mock.patch('core.platform._proc_nvidia_gpus', return_value=[]):
                with mock.patch.dict(os.environ, {
                    'OTACON_WINDOWS_GPU_HINT': 'NVIDIA GeForce RTX 4090',
                    'OTACON_WINDOWS_GPU_VRAM_GB': '24.0',
                }, clear=False):
                    h = detect()
        self.assertEqual(len(h.gpus), 1)
        self.assertEqual(h.gpus[0].model, 'NVIDIA GeForce RTX 4090')
        self.assertEqual(h.gpus[0].vram_gb, 24.0)
        self.assertIn('WINDOWS_GPU_HINT', h.gpu_detection['message'])


if __name__ == '__main__':
    unittest.main()
