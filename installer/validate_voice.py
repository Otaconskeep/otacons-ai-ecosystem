"""validate-voice: resolve agent voice through the production TTS path."""
from __future__ import annotations

import argparse
import os
import sys

from core.deployment import local_deployment
from core.voice import (
    assert_audible_speech,
    synthesize_voice,
    profile_for,
    profile_hash,
    TTSError,
    TTS_READY,
    validate_wav,
)


def resolve_agent(name: str) -> dict:
    key = (name or 'Billy').strip().lower()
    known = {
        'billy': {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001'},
        'sarah': {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002'},
    }
    if key in known:
        return known[key]
    return {'id': 'agent_custom', 'display_name': name, 'voice_id': os.getenv('OTACON_VOICE_ID', 'voice_001')}


def main(argv=None):
    p = argparse.ArgumentParser(prog='otacon-backend validate-voice')
    p.add_argument('--agent', default='Billy')
    p.add_argument('--text', default=None)
    p.add_argument('--real', action='store_true', help='Use Piper/Wyoming endpoint from OTACON_TTS_ENDPOINT')
    args = p.parse_args(argv)

    agent = resolve_agent(args.agent)
    text = args.text or f'Hello, I am {agent["display_name"]}.'

    if args.real:
        endpoint = os.getenv('OTACON_TTS_ENDPOINT')
        if not endpoint:
            print('REAL_TTS_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT')
            print('Set OTACON_TTS_ENDPOINT=wyoming://host:port and OTACON_TTS_PROVIDER=piper')
            print('Then: otacon-backend validate-voice --agent Billy --real')
            return 2
        provider = os.getenv('OTACON_TTS_PROVIDER', 'piper')
        # Allow override; default keeps Billy → voice_001 (Warm Male / Bryce Piper).
        if os.getenv('OTACON_VOICE_ID'):
            agent = dict(agent)
            agent['voice_id'] = os.getenv('OTACON_VOICE_ID')
        deployment = local_deployment(tts_endpoint=endpoint, tts_provider=provider)
        mode = 'REAL'
        purpose = 'preview'
    else:
        os.environ['OTACON_ALLOW_TEST_TTS'] = '1'
        deployment = local_deployment(tts_endpoint='test://tts', tts_provider='test')
        mode = 'SANDBOX'
        purpose = 'validate-voice'

    print(f'Mode: {mode}')
    print(f'Agent: {agent["display_name"]} ({agent["id"]})')
    try:
        profile = profile_for(agent['voice_id'])
        print(f'Voice: {profile.id} ({profile.display_name})')
        print(f'Provider (profile): {profile.provider}')
        print(f'Profile hash: {profile_hash(profile)}')
        if profile.fixture:
            print('License: TEST FIXTURE')
        else:
            print(f'License: {profile.license}')
            print(f'Source: {profile.source}')

        result = synthesize_voice(deployment, agent, text, purpose=purpose)
        validate_wav(result['bytes'])
        if mode == 'REAL':
            audible = assert_audible_speech(result['bytes'])
            print(f'Audible: duration={audible["duration_sec"]:.3f}s peak={audible.get("peak")}')
            if result.get('provider') == 'test':
                print('Detail: REAL mode resolved TestTTSProvider — Piper is not wired')
                print('Result: FAIL')
                return 1
        print(f'Service: {result["service_id"]}')
        print(f'Provider (resolved): {result["provider"]}')
        print(f'Health: {result.get("health", TTS_READY)}')
        print(f'Resolved profile: {result["resolved_synthesis"]}')
        print(f'Audio: {result["format"]} {result["sample_rate"]} Hz, {len(result["bytes"])} bytes, path={result["audio_path"]}')
        print('Result: PASS')
        if mode == 'SANDBOX':
            print('TEST_TTS_PASS')
            print('REAL_TTS_ACCEPTANCE_PENDING')
            print('External acceptance command:')
            print('  OTACON_TTS_PROVIDER=piper OTACON_TTS_ENDPOINT=wyoming://<host>:<port> \\')
            print('    otacon-backend validate-voice --agent Billy --real')
        else:
            print('REAL_TTS_PASS')
        return 0
    except TTSError as e:
        print(f'Health/Error: {e.code}')
        print(f'Detail: {e.message}')
        print('Result: FAIL')
        if mode == 'SANDBOX':
            print('REAL_TTS_ACCEPTANCE_PENDING')
        else:
            print('REAL_TTS_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT')
        return 1
    except Exception as e:
        print(f'Health/Error: SYNTHESIS_FAILED')
        print(f'Detail: {e}')
        print('Result: FAIL')
        return 1


if __name__ == '__main__':
    sys.exit(main())
