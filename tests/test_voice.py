import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.voice import (
    VoiceProfile,
    synthesize,
    synthesize_voice,
    profile_for,
    profile_hash,
    resolve_synthesis_settings,
    TestTTSProvider,
    FailingTTSProvider,
    PiperProvider,
    TTSError,
    PROVIDER_DEFAULTS,
    validate_wav,
)
from core.deployment import local_deployment, tts_service
from core.topology import Deployment, Host
from core.agent_service import chat_with_optional_speech
from core.providers import TestProvider
from core.actions import action_plan, run_voice_actions, TTS_ACTIONS
from core.router import resolve


class VoiceTests(unittest.TestCase):
    def setUp(self):
        # Architecture unit tests intentionally exercise TestTTSProvider.
        os.environ['OTACON_ALLOW_TEST_TTS'] = '1'
        os.environ['OTACON_TTS_PROVIDER'] = 'test'
        os.environ['OTACON_TTS_ENDPOINT'] = 'test://tts'
        os.environ['OTACON_SHOW_TEST_VOICES'] = '1'

    def test_profiles_and_isolation(self):
        a = synthesize({'voice_id': 'voice_001'}, 'x')
        b = synthesize({'voice_id': 'voice_002'}, 'x')
        self.assertNotEqual(a['voice_id'], b['voice_id'])
        self.assertEqual(a['synthesis']['length_scale'], 1.0)
        self.assertEqual(b['synthesis']['length_scale'], 1.25)

    def test_assert_audible_rejects_test_beep(self):
        from core.voice import assert_audible_speech, TestTTSProvider, profile_for
        raw = TestTTSProvider().synthesize('hi', profile_for('test_voice_measured'))
        with self.assertRaises(TTSError):
            assert_audible_speech(raw['bytes'])

    def test_test_tts_blocked_without_allow_flag(self):
        os.environ.pop('OTACON_ALLOW_TEST_TTS', None)
        d = local_deployment(tts_provider='test', tts_endpoint='test://tts')
        with self.assertRaises(TTSError):
            synthesize_voice(d, {'id': 'a', 'display_name': 'Billy', 'voice_id': 'voice_002'}, 'Hello', purpose='preview')
        os.environ['OTACON_ALLOW_TEST_TTS'] = '1'

    def test_invalid_profile(self):
        with self.assertRaises(ValueError):
            VoiceProfile('x', 'x', 'test', 'x', synthesis={'noise_w': 0}).validate()

    def test_audio_result(self):
        self.assertTrue(synthesize({'voice_id': 'voice_001'}, 'x')['bytes'].startswith(b'RIFF'))

    def test_missing_voice(self):
        with self.assertRaises(LookupError):
            synthesize({'voice_id': 'missing'}, 'x')

    def test_piper_endpoint_is_configured(self):
        p = PiperProvider('wyoming://voice-service:10200')
        self.assertEqual(p.endpoint, 'wyoming://voice-service:10200')

    def test_profile_identity_is_stable(self):
        self.assertEqual(profile_hash(profile_for('voice_001')), profile_hash(profile_for('voice_001')))

    def test_test_fixtures_are_marked(self):
        self.assertFalse(profile_for('voice_001').fixture)
        self.assertFalse(profile_for('voice_002').fixture)
        self.assertTrue(profile_for('test_voice_warm').fixture)
        self.assertTrue(profile_for('test_voice_measured').fixture)
        self.assertIn('TEST FIXTURE', profile_for('test_voice_warm').license)
        self.assertIn('piper', profile_for('voice_002').provider)
        self.assertEqual(profile_for('voice_002').model, 'en_US-hfc_female-medium')
        self.assertEqual(profile_for('voice_002').display_name, 'Measured Female')

    def test_global_default_regression_voice_A_keeps_explicit(self):
        """Permanent regression: explicit per-voice settings beat service defaults."""
        voice_A = VoiceProfile(
            'voice_A', 'A', 'test', 'm',
            synthesis={'length_scale': 1.0, 'noise_scale': 0.667, 'noise_w': 0.8},
            fixture=True,
            license='TEST FIXTURE',
        )
        service_defaults = {'length_scale': 1.25, 'noise_scale': 0.95, 'noise_w': 0.95}
        resolved = resolve_synthesis_settings(voice_A, None, service_defaults)
        self.assertEqual(resolved['length_scale'], 1.0)
        self.assertEqual(resolved['noise_scale'], 0.667)
        self.assertEqual(resolved['noise_w'], 0.8)
        out = TestTTSProvider().synthesize('hello', voice_A, defaults=service_defaults)
        self.assertEqual(out['synthesis']['length_scale'], 1.0)
        self.assertEqual(out['synthesis']['noise_scale'], 0.667)
        self.assertEqual(out['synthesis']['noise_w'], 0.8)

    def test_global_default_regression_voice_B_inherits_service(self):
        voice_B = VoiceProfile('voice_B', 'B', 'test', 'm', synthesis={}, fixture=True, license='TEST FIXTURE')
        service_defaults = {'length_scale': 1.25, 'noise_scale': 0.95, 'noise_w': 0.95}
        resolved = resolve_synthesis_settings(voice_B, None, service_defaults)
        self.assertEqual(resolved['length_scale'], 1.25)
        self.assertEqual(resolved['noise_scale'], 0.95)
        self.assertEqual(resolved['noise_w'], 0.95)

    def test_production_override_wins(self):
        p = profile_for('voice_001')
        resolved = resolve_synthesis_settings(
            p,
            {'length_scale': 1.5},
            {'length_scale': 1.25, 'noise_scale': 0.95, 'noise_w': 0.95},
        )
        self.assertEqual(resolved['length_scale'], 1.5)
        self.assertEqual(resolved['noise_scale'], 0.667)

    def test_billy_sarah_isolation_via_router(self):
        d = local_deployment(tts_provider='test', tts_endpoint='test://tts')
        phrase = 'The same spoken phrase.'
        billy = synthesize_voice(d, {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001'}, phrase)
        sarah = synthesize_voice(d, {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002'}, phrase)
        self.assertEqual(billy['voice_id'], 'voice_001')
        self.assertEqual(sarah['voice_id'], 'voice_002')
        self.assertNotEqual(billy['resolved_synthesis'], sarah['resolved_synthesis'])
        self.assertEqual(billy['service_id'], sarah['service_id'])
        self.assertIn('agent_id', billy['trace'])

    def test_preview_production_parity(self):
        d = local_deployment(tts_provider='test', tts_endpoint='test://tts')
        agent = {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001'}
        text = 'Parity check phrase.'
        preview = synthesize_voice(d, agent, text, purpose='preview')
        production = synthesize_voice(d, agent, text, purpose='production')
        for key in ('voice_id', 'provider', 'service_id'):
            self.assertEqual(preview[key], production[key], key)
        self.assertEqual(preview['resolved_synthesis'], production['resolved_synthesis'])
        self.assertEqual(preview['profile_id'], production['profile_id'])

    def test_tts_failure_does_not_break_chat(self):
        d = local_deployment()
        agent = {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001'}
        result = chat_with_optional_speech(
            d, agent, 'What is your name?',
            provider=TestProvider(), auto_speak=True, tts_provider=FailingTTSProvider(),
        )
        self.assertEqual(result['text'], 'My name is Billy.')
        self.assertEqual(result['voice']['status'], 'error')
        self.assertEqual(result['voice']['message'], 'Voice playback unavailable')
        self.assertEqual(result['voice']['code'], 'SYNTHESIS_FAILED')

    def test_text_to_speech_capability_routing(self):
        d = local_deployment(tts_provider='test')
        a = resolve(d, 'text_to_speech')
        self.assertEqual(a.service_id, 'service_tts_001')
        self.assertEqual(a.defaults['length_scale'], 1.25)

    def test_audio_cache_outside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            d = local_deployment(tts_provider='test')
            r = synthesize_voice(
                d, {'id': 'agent_001', 'voice_id': 'voice_001'}, 'cache me',
                cache_dir=Path(td),
            )
            self.assertTrue(Path(r['audio_path']).is_file())
            self.assertTrue(str(r['audio_path']).startswith(td))
            validate_wav(r['bytes'])

    def test_installer_voice_actions(self):
        plan = action_plan(['chat', 'voice'])
        ids = [a.id for a in plan]
        for aid, _ in TTS_ACTIONS:
            self.assertIn(aid, ids)
        d = local_deployment(tts_provider='test')
        actions = run_voice_actions(d, {'id': 'agent_001', 'voice_id': 'voice_001'})
        self.assertTrue(all(a.state == 'SUCCEEDED' for a in actions), [a.error for a in actions if a.state != 'SUCCEEDED'])

    def test_agent_service_has_no_hardcoded_wyoming(self):
        import core.agent_service as mod
        src = Path(mod.__file__).read_text()
        self.assertNotIn('10200', src)
        self.assertNotIn('localhost', src)
        self.assertNotIn('127.0.0.1', src)
        self.assertNotIn('piper-wyoming', src)


class WyomingParseTests(unittest.TestCase):
    def test_parse_endpoint(self):
        from core.wyoming_transport import parse_endpoint
        self.assertEqual(parse_endpoint('wyoming://voice.example:10200'), ('voice.example', 10200))
        self.assertEqual(parse_endpoint('tcp://host:9'), ('host', 9))


if __name__ == '__main__':
    unittest.main()
