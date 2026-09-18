"""Video Studio setup orchestrator — mocked regression matrix (A–L)."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from expansion.capabilities import studio_setup as ss
from expansion.state_layout import resolve_layout


class _Report:
    def __init__(self, state: str, detail: str = '', discovery: dict | None = None):
        self.state = state
        self.detail = detail
        self.discovery = discovery or {}

    def to_dict(self):
        return {'state': self.state, 'detail': self.detail, 'discovery': self.discovery}


class StudioSetupOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(root / 'data'),
        }
        self._cm = mock.patch.dict(os.environ, self.env, clear=False)
        self._cm.start()
        self.layout = resolve_layout(product_root=Path(__file__).resolve().parents[1] / 'expansion')
        self.layout.ensure_user_dirs()
        ss._WORKER = None

    def tearDown(self):
        # Drain any background worker
        w = ss._WORKER
        if w is not None and w.is_alive():
            w.join(timeout=5)
        ss._WORKER = None
        self._cm.stop()
        self.tmp.cleanup()

    def _not_ready(self):
        return _Report('NOT_CONFIGURED', discovery={'endpoint': ''})

    def _ready(self, endpoint='http://127.0.0.1:8188'):
        return _Report('READY', discovery={'endpoint': endpoint})

    def test_A_docker_ready_comfy_missing_provisions(self):
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(),  # start gate
            self._ready(),      # finish verify
            self._ready(),      # setup_status after
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_wait_docker_ready', return_value=(True, {'ok': True})), \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={
                 'ok': True, 'endpoint': 'http://127.0.0.1:8188',
             }) as ensure, \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint') as save, \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True, 'status': 'ready'}), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=True):
            out = ss.start_studio_setup(layout=self.layout, background=False)
            self.assertEqual(out.get('action'), 'completed')
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            self.assertTrue(st['ok'])
            ensure.assert_called()
            save.assert_called()

    def test_B_docker_stopped_launches_then_continues(self):
        calls = {'n': 0}

        def docker_probe(*_a, **_k):
            calls['n'] += 1
            if calls['n'] < 3:
                return {'ok': False, 'status': 'daemon_down', 'detail': 'error during connect'}
            return {'ok': True, 'status': 'ready', 'detail': 'up'}

        with mock.patch.object(ss, 'probe_video_studio', side_effect=lambda *a, **k: (
            self._ready() if calls['n'] >= 3 else self._not_ready()
        )), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, 'probe_docker_engine', side_effect=docker_probe), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=True), \
             mock.patch.object(ss, 'try_start_docker_desktop', return_value={'ok': True, 'action': 'launched'}) as launch, \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={'ok': True, 'endpoint': 'http://127.0.0.1:8188'}), \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint'), \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss.time, 'sleep', return_value=None):
            # Fix probe: start gate needs NOT_CONFIGURED; finish needs READY
            pass

        probe_seq = [self._not_ready()]

        def probe(*_a, **_k):
            if len(probe_seq) == 1:
                # After docker comes up, verification returns READY
                if calls['n'] >= 3:
                    return self._ready()
                return self._not_ready()
            return probe_seq[0]

        with mock.patch.object(ss, 'probe_video_studio', side_effect=probe), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, 'probe_docker_engine', side_effect=docker_probe), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=True), \
             mock.patch.object(ss, 'try_start_docker_desktop', return_value={'ok': True, 'action': 'launched'}) as launch, \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={'ok': True, 'endpoint': 'http://127.0.0.1:8188'}), \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint'), \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss.time, 'sleep', return_value=None):
            out = ss.start_studio_setup(layout=self.layout, background=False)
            self.assertEqual(out.get('action'), 'completed')
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            launch.assert_called()

    def test_C_existing_comfy_8188_no_duplicate_install(self):
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(), self._ready(), self._ready(),
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={
                 'found': True, 'endpoint': 'http://127.0.0.1:8188', 'source': 'detected', 'detail': 'ok',
             }), \
             mock.patch.object(ss, 'ensure_comfy_sidecar') as ensure, \
             mock.patch.object(ss, 'save_studio_endpoint') as save, \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            out = ss.start_studio_setup(layout=self.layout, background=False)
            self.assertEqual(out.get('action'), 'completed')
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            ensure.assert_not_called()
            save.assert_called_once()

    def test_D_managed_stopped_starts(self):
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(), self._ready(), self._ready(),
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_wait_docker_ready', return_value=(True, {'ok': True})), \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': True, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={
                 'ok': True, 'endpoint': 'http://127.0.0.1:8188',
             }) as ensure, \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint'), \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            ss.start_studio_setup(layout=self.layout, background=False)
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            ensure.assert_called()

    def test_E_already_ready_skips_setup_screen_path(self):
        with mock.patch.object(ss, 'probe_video_studio', return_value=self._ready()), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={
                 'found': True, 'endpoint': 'http://127.0.0.1:8188', 'source': 'saved',
             }), \
             mock.patch.object(ss, '_managed_container_status', return_value={}), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=True):
            out = ss.start_studio_setup(layout=self.layout, background=False)
            self.assertEqual(out.get('action'), 'already_ready')
            self.assertEqual(out.get('phase'), ss.READY)

    def test_F_stale_endpoint_rediscovers(self):
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(), self._ready(), self._ready(),
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={
                 'found': False, 'endpoint': 'http://127.0.0.1:9999', 'source': 'stale',
             }), \
             mock.patch.object(ss, '_wait_docker_ready', return_value=(True, {'ok': True})), \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={
                 'ok': True, 'endpoint': 'http://127.0.0.1:8188',
             }), \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint') as save, \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            ss.start_studio_setup(layout=self.layout, background=False)
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            self.assertIsNotNone(save.call_args)
            self.assertEqual(save.call_args.args[0], 'http://127.0.0.1:8188')

    def test_G_no_required_assets_no_redownload(self):
        self.assertEqual(ss.required_studio_assets(), [])

    def test_H_interrupted_resume_via_second_start(self):
        ss.save_setup_state({
            **ss._default_state(),
            'phase': ss.INSTALLING_COMFY,
            'running': False,
            'attempt': 1,
        }, layout=self.layout)
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(), self._ready(), self._ready(),
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_wait_docker_ready', return_value=(True, {'ok': True})), \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={
                 'ok': True, 'endpoint': 'http://127.0.0.1:8188',
             }), \
             mock.patch.object(ss, 'comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch.object(ss, 'save_studio_endpoint'), \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            out = ss.start_studio_setup(layout=self.layout, background=False)
            self.assertEqual(out.get('action'), 'completed')
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)
            self.assertGreaterEqual(int(st.get('attempt') or 0), 2)

    def test_I_double_click_no_second_worker(self):
        entered = {'n': 0}
        hold = threading.Event()
        release = threading.Event()

        def slow_orch(layout):
            entered['n'] += 1
            hold.set()
            release.wait(timeout=5)
            ss._set_phase(ss.load_setup_state(layout), ss.READY, aria='done', layout=layout)

        with mock.patch.object(ss, '_orchestrate', side_effect=slow_orch), \
             mock.patch.object(ss, 'probe_video_studio', return_value=self._not_ready()), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': False}), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_managed_container_status', return_value={}), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=False):
            a = ss.start_studio_setup(layout=self.layout, background=True)
            self.assertTrue(hold.wait(timeout=2))
            b = ss.start_studio_setup(layout=self.layout, background=True)
            release.set()
            if ss._WORKER:
                ss._WORKER.join(timeout=5)
            self.assertEqual(a.get('action'), 'started')
            self.assertEqual(b.get('action'), 'already_running')
            self.assertEqual(entered['n'], 1)

    def test_J_backend_failure_human_readable(self):
        with mock.patch.object(ss, 'probe_video_studio', return_value=self._not_ready()), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_wait_docker_ready', return_value=(True, {'ok': True})), \
             mock.patch.object(ss, '_managed_container_status', return_value={'exists': False, 'running': False}), \
             mock.patch.object(ss, 'ensure_comfy_sidecar', return_value={
                 'ok': False,
                 'action': 'docker_daemon_down',
                 'error': 'error during connect: open //./pipe/dockerDesktopLinuxEngine',
                 'hint': (
                     "Docker Desktop is installed but isn't running yet. "
                     "Start Docker Desktop and I'll continue automatically."
                 ),
             }), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            ss.start_studio_setup(layout=self.layout, background=False)
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.FAILED)
            self.assertNotIn('dockerDesktopLinuxEngine', st.get('aria') or '')
            blob = (st.get('aria') or '') + (st.get('error') or '')
            self.assertIn('Docker', blob)
            self.assertTrue(st.get('technical'))

    def test_K_cpu_path_no_crash(self):
        with mock.patch.object(ss, 'probe_video_studio', side_effect=[
            self._not_ready(), self._ready(), self._ready(),
        ]), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={
                 'found': True, 'endpoint': 'http://127.0.0.1:8188', 'source': 'detected',
             }), \
             mock.patch.object(ss, 'save_studio_endpoint'), \
             mock.patch.object(ss, 'required_studio_assets', return_value=[]), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={'ok': True}):
            ss.start_studio_setup(layout=self.layout, background=False)
            st = ss.load_setup_state(self.layout)
            self.assertEqual(st['phase'], ss.READY)

    def test_L_diagnostics_expose_technical(self):
        with mock.patch.object(ss, 'probe_video_studio', return_value=self._not_ready()), \
             mock.patch.object(ss, 'probe_docker_engine', return_value={
                 'ok': False, 'status': 'daemon_down', 'detail': 'pipe',
             }), \
             mock.patch.object(ss, '_prefer_endpoint', return_value={'found': False}), \
             mock.patch.object(ss, '_managed_container_status', return_value={}), \
             mock.patch.object(ss, 'docker_desktop_installed', return_value=True):
            status = ss.setup_status(layout=self.layout)
            self.assertIn('diagnostics', status)
            self.assertIn('docker', status['diagnostics'])
            self.assertTrue(status['need_setup'])

    def test_probe_detail_no_env_var_leak(self):
        from expansion.capabilities import video_studio as vs
        with mock.patch.object(vs, '_discover_endpoint', return_value={
            'endpoint': '', 'provider': 'none', 'config_path': '', 'core_video_module': True,
        }), mock.patch.object(vs, '_forbidden_private_paths', return_value=[]):
            r = vs.probe_video_studio(self.layout)
        self.assertEqual(r.state, 'NOT_CONFIGURED')
        self.assertNotIn('OTACON_COMFYUI_URL', r.detail)
        self.assertNotIn('video_studio.json', r.detail)


if __name__ == '__main__':
    unittest.main()
