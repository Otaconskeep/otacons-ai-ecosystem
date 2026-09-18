"""Comfy sidecar detect / start contract tests (no live Docker required)."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from expansion.capabilities import comfy_sidecar as cs


class TestComfySidecar(unittest.TestCase):
    def test_compose_file_exists(self):
        self.assertTrue(cs.compose_file().is_file())

    def test_detect_prefers_first_healthy_port(self):
        with mock.patch(
            'expansion.capabilities.comfy_sidecar.comfy_endpoint_healthy',
            side_effect=[(False, 'down'), (True, '/system_stats → 200')],
        ):
            d = cs.detect_local_comfy()
        self.assertTrue(d['found'])
        self.assertEqual(d['endpoint'], 'http://127.0.0.1:8199')

    def test_ensure_already_running_saves(self):
        with mock.patch(
            'expansion.capabilities.comfy_sidecar.detect_local_comfy',
            return_value={'found': True, 'endpoint': 'http://127.0.0.1:8188', 'detail': 'ok'},
        ), mock.patch(
            'expansion.capabilities.comfy_sidecar.save_studio_endpoint',
            return_value={'ok': True, 'state': 'READY', 'detail': 'ok', 'video_studio': {}},
        ):
            out = cs.ensure_comfy_sidecar()
        self.assertTrue(out['ok'])
        self.assertEqual(out['action'], 'already_running')

    def test_ensure_reports_docker_missing(self):
        with mock.patch(
            'expansion.capabilities.comfy_sidecar.detect_local_comfy',
            return_value={'found': False},
        ), mock.patch(
            'expansion.capabilities.comfy_sidecar.probe_docker_engine',
            return_value={
                'ok': False,
                'status': 'missing',
                'detail': 'Docker CLI not found',
                'hint': 'Install Docker Desktop',
            },
        ):
            out = cs.ensure_comfy_sidecar()
        self.assertFalse(out['ok'])
        self.assertEqual(out['action'], 'missing')

    def test_ensure_reports_daemon_down_before_compose(self):
        with mock.patch(
            'expansion.capabilities.comfy_sidecar.detect_local_comfy',
            return_value={'found': False},
        ), mock.patch(
            'expansion.capabilities.comfy_sidecar.probe_docker_engine',
            return_value={
                'ok': False,
                'status': 'daemon_down',
                'detail': 'error during connect',
                'hint': 'Start Docker Desktop',
            },
        ):
            out = cs.ensure_comfy_sidecar()
        self.assertFalse(out['ok'])
        self.assertEqual(out['action'], 'daemon_down')
        self.assertIn('Docker Desktop', out.get('hint', ''))

    def test_compose_failure_hint_connect(self):
        action, hint = cs._compose_failure_hint(
            'Error response from daemon: unable to get image '
            "'yanwk/comfyui-boot:cpu': error during connect: Get ..."
        )
        self.assertEqual(action, 'docker_daemon_down')
        self.assertIn('Docker', hint)

    def test_docker_connect_failure_needles(self):
        self.assertTrue(cs._docker_connect_failure('error during connect: Get http://...'))
        self.assertTrue(cs._docker_connect_failure('Cannot connect to the Docker daemon'))
        self.assertFalse(cs._docker_connect_failure('image already exists'))


if __name__ == '__main__':
    unittest.main()
