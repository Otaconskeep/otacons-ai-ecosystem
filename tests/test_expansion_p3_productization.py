"""P3 productization + protected release acceptance tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.capabilities.discord_n8n import probe_discord, probe_n8n, probe_all_optional
from expansion.capabilities.home_assistant import probe_home_assistant, save_ha_config
from expansion.capabilities.video_studio import probe_video_studio, studio_runtime_context
from expansion.emotion_store import EmotionStore
from expansion.protected.aead import (
    decrypt_aes_gcm, derive_key_argon2id, encrypt_aes_gcm, generate_bundle_key,
)
from expansion.protected.bundle import load_dossier_from_bundle, write_protected_bundle
from expansion.protected.keys import PermissionedFileKeyProvider, default_key_provider
from expansion.protected.loader import BUNDLE_KEY_NAME, ProtectedResourceLoader
from expansion.protected.signing import generate_signing_keypair, sign_manifest, verify_manifest_signature
from expansion.protected.verify import reject_tampered, verify_protected_package
from expansion.release.build import build_dev_tree, build_protected_release
from expansion.release.compile_eval import evaluate_compile_candidates
from expansion.release.frontend import harden_frontend_tree, rough_minify_js
from expansion.release.layout import assert_no_plaintext_dossiers_in_release
from expansion.release.update import apply_protected_update, rollback_to_previous, switch_current, stage_package
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout
from expansion.manifest import PackageManifest, build_dev_manifest
from expansion.versions import MANIFEST_SCHEMA_VERSION, current_versions


class P3LayoutCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_SECRETS_ROOT': str(self.root / 'cfg' / 'secrets'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()


class TestP3A_Capabilities(P3LayoutCase):
    def test_video_studio_unavailable_without_endpoint(self):
        # Clear comfy urls — contracts alone must NOT fake LIMITED/READY
        with mock.patch.dict(os.environ, {'OTACON_COMFYUI_URL': '', 'COMFYUI_URL': ''}, clear=False):
            r = probe_video_studio(self.layout)
        self.assertEqual(r.state, 'NOT_CONFIGURED')
        self.assertTrue(r.optional)
        self.assertEqual(r.owner_agent, 'muse')

    def test_video_studio_ready_when_comfy_healthy(self):
        with mock.patch.dict(os.environ, {'OTACON_COMFYUI_URL': 'http://127.0.0.1:8188'}, clear=False):
            with mock.patch(
                'expansion.capabilities.video_studio.comfy_endpoint_healthy',
                return_value=(True, '/system_stats → 200'),
            ):
                r = probe_video_studio(self.layout)
        self.assertEqual(r.state, 'READY')

    def test_video_studio_setup_when_endpoint_down(self):
        """Stale :8188 must not stick as LIMITED — honest SETUP (NOT_CONFIGURED)."""
        prefs = self.layout.user_preferences
        prefs.mkdir(parents=True, exist_ok=True)
        (prefs / 'video_studio.json').write_text(
            json.dumps({'endpoint': 'http://127.0.0.1:8188', 'provider': 'comfyui'}) + '\n',
            encoding='utf-8',
        )
        with mock.patch.dict(os.environ, {'OTACON_COMFYUI_URL': '', 'COMFYUI_URL': ''}, clear=False):
            with mock.patch(
                'expansion.capabilities.video_studio.comfy_endpoint_healthy',
                return_value=(False, 'connection refused'),
            ):
                r = probe_video_studio(self.layout)
        self.assertEqual(r.state, 'NOT_CONFIGURED')
        self.assertIn('Set Up', r.detail)
        self.assertFalse((prefs / 'video_studio.json').is_file())

    def test_video_studio_rejects_private_lan(self):
        topo_path = self.layout.user_preferences / 'topology.json'
        topo_path.parent.mkdir(parents=True, exist_ok=True)
        topo_path.write_text(json.dumps({
            'schema_version': 1,
            'comfyui_url': 'http://192.168.50.219:8188',
        }) + '\n', encoding='utf-8')
        r = probe_video_studio(self.layout)
        self.assertEqual(r.state, 'FAILED')
        self.assertIn('forbidden', r.detail)

    def test_studio_context_from_shared_runtime(self):
        ctx = studio_runtime_context('muse')
        self.assertEqual(ctx.get('persona_source'), 'expansion.runtime')
        self.assertNotIn('system_prompt', ctx)

    def test_ha_missing_does_not_break(self):
        r = probe_home_assistant(self.layout)
        self.assertEqual(r.state, 'UNAVAILABLE')
        # Foundation still works
        self.assertTrue(ExpansionRuntime(self.layout).expansion_enabled())

    def test_ha_config_ready_without_token_is_limited(self):
        save_ha_config('http://127.0.0.1:8123', token='', layout=self.layout)
        r = probe_home_assistant(self.layout)
        self.assertEqual(r.state, 'LIMITED')

    def test_discord_n8n_optional(self):
        self.assertEqual(probe_discord(self.layout).state, 'UNAVAILABLE')
        self.assertEqual(probe_n8n(self.layout).state, 'UNAVAILABLE')
        allc = probe_all_optional(self.layout)
        self.assertIn('video_studio', allc)
        self.assertIn('home_assistant', allc)


class TestP3_CryptoSigning(P3LayoutCase):
    def test_aes_gcm_roundtrip(self):
        key = generate_bundle_key()
        blob = encrypt_aes_gcm(b'hello-keep', key, aad=b'test')
        self.assertEqual(decrypt_aes_gcm(blob, key), b'hello-keep')
        wire = blob.to_wire()
        from expansion.protected.aead import EncryptedBlob
        self.assertEqual(decrypt_aes_gcm(EncryptedBlob.from_wire(wire), key), b'hello-keep')

    def test_wrong_key_rejected(self):
        key = generate_bundle_key()
        blob = encrypt_aes_gcm(b'secret', key)
        with self.assertRaises(Exception):
            decrypt_aes_gcm(blob, generate_bundle_key())

    def test_argon2id_derive(self):
        salt = os.urandom(16)
        k1 = derive_key_argon2id(b'pass', salt)
        k2 = derive_key_argon2id(b'pass', salt)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 32)
        self.assertNotEqual(k1, derive_key_argon2id(b'other', salt))

    def test_sign_and_verify_manifest(self):
        pair = generate_signing_keypair('t1')
        m = build_dev_manifest()
        m.channel = 'protected'
        m.build_id = 'b1'
        m.artifacts = []
        # protected requires artifacts — add dummy file hash
        from expansion.manifest import ArtifactRef
        m.artifacts = [ArtifactRef(path='protected-bundle.enc', sha256='a' * 64,
                                   role='encrypted_bundle', encrypted=True, aead='AES-256-GCM')]
        sign_manifest(m, pair.private_key_pem, key_id='t1')
        self.assertEqual(verify_manifest_signature(m, pair.public_key_pem), [])
        m.signature = 'AAAA'
        self.assertTrue(verify_manifest_signature(m, pair.public_key_pem))


class TestP3_KeyProvider(P3LayoutCase):
    def test_permissioned_store_load(self):
        kp = PermissionedFileKeyProvider(layout=self.layout)
        kp.store('testkey', b'\x01\x02' * 16)
        self.assertEqual(kp.load('testkey'), b'\x01\x02' * 16)
        path = self.layout.secrets_root / 'testkey.key'
        self.assertTrue(path.is_file())
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_default_provider_no_plaintext_in_json(self):
        kp = default_key_provider(self.layout)
        kp.store(BUNDLE_KEY_NAME, generate_bundle_key())
        # preferences must not contain key material dump
        for path in self.layout.user_preferences.glob('*.json'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('expansion-bundle', text)


class TestP3_BundleAndRelease(P3LayoutCase):
    def test_write_and_load_protected_bundle(self):
        out = self.root / 'bundle_out'
        result = write_protected_bundle(out, layout=self.layout)
        self.assertTrue(result.bundle_path.is_file())
        wire = result.bundle_path.read_bytes()
        aria = load_dossier_from_bundle(wire, result.key, 'aria')
        self.assertEqual(aria['agent_id'], 'aria')

    def test_protected_release_build_smoke(self):
        out = self.root / 'prot'
        ui = self.root / 'ui_src'
        ui.mkdir()
        (ui / 'app.js').write_text(
            'console.log(1);\n//# sourceMappingURL=app.js.map\n', encoding='utf-8',
        )
        (ui / 'app.js.map').write_text('{"version":3}', encoding='utf-8')
        kp = PermissionedFileKeyProvider(layout=self.layout)
        result = build_protected_release(
            out, layout=self.layout, key_provider=kp, minify_frontend_from=ui,
        )
        self.assertTrue(result.smoke_ok, result.notes)
        self.assertEqual(result.channel, 'protected')
        self.assertEqual(assert_no_plaintext_dossiers_in_release(out), [])
        self.assertFalse((out / 'runtime' / 'ui' / 'app.js.map').exists())
        ui_js = (out / 'runtime' / 'ui' / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn('sourceMappingURL', ui_js)

        vr = verify_protected_package(out, public_key_pem=result.public_key_pem)
        self.assertTrue(vr.ok, vr.errors)

        loader = ProtectedResourceLoader(
            layout=self.layout, key_provider=kp, channel='protected', package_dir=out,
        )
        d = loader.load_canonical_dossier('vector')
        self.assertEqual(d.agent_id, 'vector')

    def test_tampered_package_rejected(self):
        out = self.root / 'prot2'
        kp = PermissionedFileKeyProvider(layout=self.layout)
        result = build_protected_release(out, layout=self.layout, key_provider=kp)
        # Tamper ciphertext
        bundle = out / 'protected-bundle.enc'
        data = bytearray(bundle.read_bytes())
        data[-5] ^= 0x5A
        bundle.write_bytes(bytes(data))
        vr = reject_tampered(out, result.public_key_pem)
        self.assertFalse(vr.ok)
        self.assertTrue(vr.preserve_user_data)
        self.assertEqual(vr.action, 'reinstall')

    def test_missing_key_rejected_safely(self):
        out = self.root / 'prot3'
        kp = PermissionedFileKeyProvider(layout=self.layout)
        result = build_protected_release(out, layout=self.layout, key_provider=kp)
        kp.delete(BUNDLE_KEY_NAME)
        loader = ProtectedResourceLoader(
            layout=self.layout, key_provider=kp, channel='protected', package_dir=out,
        )
        with self.assertRaises(KeyError):
            loader.load_canonical_dossier('aria')
        # User emotion state still intact
        self.assertIsNotNone(EmotionStore(self.layout).get('aria'))

    def test_dev_build_keeps_plaintext_dossiers(self):
        out = self.root / 'dev'
        result = build_dev_tree(out, layout=self.layout)
        self.assertTrue(result.smoke_ok)
        self.assertTrue((out / 'product' / 'dossiers' / 'aria.json').is_file())


class TestP3_UpdateRollback(P3LayoutCase):
    def test_update_and_rollback(self):
        kp = PermissionedFileKeyProvider(layout=self.layout)
        v1 = self.root / 'pkg-v1'
        v2 = self.root / 'pkg-v2'
        r1 = build_protected_release(v1, layout=self.layout, key_provider=kp)
        # Install v1 as current
        staged1 = stage_package(v1, self.layout)
        switch_current(staged1, self.layout)
        # Build v2 with same signing keys? build generates new keys by default —
        # for update verify we need matching public key. Rebuild v2 with same pair.
        from expansion.protected.signing import generate_signing_keypair
        pair = generate_signing_keypair('upd')
        r2 = build_protected_release(
            v2, layout=self.layout, key_provider=kp,
            signing_private_pem=pair.private_key_pem,
            signing_public_pem=pair.public_key_pem,
            key_id='upd',
        )
        # Re-sign isn't needed — build already signed with pair.
        # But v1 was signed with different key — update uses r2's public key.
        # For a realistic flow: first install also with same key.
        v1b = self.root / 'pkg-v1b'
        build_protected_release(
            v1b, layout=self.layout, key_provider=kp,
            signing_private_pem=pair.private_key_pem,
            signing_public_pem=pair.public_key_pem,
            key_id='upd',
        )
        staged1 = stage_package(v1b, self.layout)
        switch_current(staged1, self.layout)

        jealousy_before = EmotionStore(self.layout).get('aria').dimensions['jealousy']
        upd = apply_protected_update(v2, layout=self.layout, public_key_pem=pair.public_key_pem)
        self.assertTrue(upd.ok, upd.errors)
        self.assertEqual(upd.action, 'updated')
        self.assertAlmostEqual(
            EmotionStore(self.layout).get('aria').dimensions['jealousy'],
            jealousy_before, places=5,
        )
        rb = rollback_to_previous(self.layout)
        self.assertTrue(rb.ok)
        self.assertEqual(rb.action, 'rolled_back')

    def test_reject_unsigned_update(self):
        bad = self.root / 'badpkg'
        bad.mkdir()
        (bad / 'PACKAGE_MANIFEST.json').write_text(
            json.dumps({
                'manifest_schema_version': MANIFEST_SCHEMA_VERSION,
                'product': 'otacon-expansion',
                'expansion_version': '9.9.9',
                'core_version_min': '0.1.0',
                'agent_schema_version': 1,
                'created_at': 1.0,
                'channel': 'protected',
                'build_id': 'x',
                'artifacts': [{
                    'path': 'protected-bundle.enc',
                    'sha256': 'b' * 64,
                    'role': 'encrypted_bundle',
                    'encrypted': True,
                    'aead': 'AES-256-GCM',
                }],
                'signature': '',
                'signing_key_id': '',
            }) + '\n', encoding='utf-8',
        )
        pair = generate_signing_keypair('x')
        res = apply_protected_update(bad, layout=self.layout, public_key_pem=pair.public_key_pem)
        self.assertFalse(res.ok)
        self.assertEqual(res.action, 'rejected')
        self.assertTrue(res.preserve_user_data)


class TestP3_FrontendAndCompile(P3LayoutCase):
    def test_minify_strips_maps(self):
        text = rough_minify_js('var a=1;\n//# sourceMappingURL=x.js.map\n')
        self.assertNotIn('sourceMappingURL', text)

    def test_harden_rejects_embedded_secret(self):
        src = self.root / 'badui'
        dest = self.root / 'outui'
        src.mkdir()
        (src / 'x.js').write_text('const api_key = "sk-abcdefghijklmnopqrstuvwxyz";\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            harden_frontend_tree(src, dest)

    def test_compile_eval_lists_priority_modules(self):
        repo = Path(__file__).resolve().parents[1]
        report = evaluate_compile_candidates(repo)
        self.assertGreaterEqual(len(report.candidates), 5)
        self.assertIn('testability', (
            report.policy + ' ' + ' '.join(report.notes)
        ).lower())


class TestP3_CoreOnlyAndKeep(unittest.TestCase):
    def test_core_only_still_imports(self):
        from expansion import emotion, schema  # noqa: F401
        layout_root = Path(tempfile.mkdtemp())
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(layout_root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(layout_root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(layout_root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            layout = resolve_layout()
            layout.ensure_user_dirs()
            self.assertFalse(ExpansionRuntime(layout).expansion_enabled())
            # Optional caps must not raise
            probe_all_optional(layout)

    def test_private_keep_not_required(self):
        self.assertFalse(str(Path(__file__)).startswith('/opt/otacon'))
        from expansion.topology import public_core_install_present
        markers = public_core_install_present()
        self.assertTrue(markers['private_keep_path_ignored'])


if __name__ == '__main__':
    unittest.main()
