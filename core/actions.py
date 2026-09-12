from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Action:
    id: str
    label: str
    state: str = 'PENDING'
    result: dict = field(default_factory=dict)
    error: dict | None = None
    technical: list[str] = field(default_factory=list)
    retries: int = 0

    def run(self, fn: Callable):
        self.state = 'RUNNING'
        try:
            self.result = fn() or {}
            self.state = 'SUCCEEDED'
            return self
        except Exception as e:
            self.state = 'FAILED'
            self.error = {'message': str(e), 'type': type(e).__name__}
            self.technical.append(repr(e))
            return self


CHAT_ACTIONS = [
    ('CHECK_LLM_RUNTIME', 'Checking AI engine'),
    ('INSTALL_LLM_RUNTIME', 'Installing AI engine'),
    ('CHECK_MODEL', 'Checking model'),
    ('CHECK_STORAGE', 'Checking model storage'),
    ('DOWNLOAD_MODEL', 'Downloading model'),
    ('START_LLM_SERVICE', 'Starting AI service'),
    ('REGISTER_LLM_SERVICE', 'Registering AI service'),
    ('VALIDATE_LLM_SERVICE', 'Validating AI service'),
    ('CREATE_AGENT', 'Creating agent'),
    ('VALIDATE_AGENT_CHAT', 'Testing agent chat'),
]

TTS_ACTIONS = [
    ('CHECK_TTS_RUNTIME', 'Checking voice service'),
    ('INSTALL_TTS_RUNTIME', 'Installing voice service'),
    ('CHECK_VOICE', 'Checking voice'),
    ('DOWNLOAD_VOICE', 'Downloading voice'),
    ('REGISTER_TTS_SERVICE', 'Registering voice service'),
    ('VALIDATE_TTS_SERVICE', 'Validating voice service'),
    ('VALIDATE_VOICE_PROFILE', 'Validating voice profile'),
    ('SYNTHESIZE_TEST_AUDIO', 'Testing speech'),
    ('ASSIGN_AGENT_VOICE', 'Assigning agent voice'),
]


def action_plan(features: list[str] | None = None):
    features = features or ['chat']
    plan = [Action(i, l) for i, l in CHAT_ACTIONS]
    if 'voice' in features or 'tts' in features:
        plan.extend(Action(i, l) for i, l in TTS_ACTIONS)
    return plan


def run_voice_actions(deployment, agent: dict, text: str = 'Voice installation check.'):
    """Execute Voice installer actions against the shared synthesize_voice path."""
    from core.voice import (
        profile_for,
        synthesize_voice,
        TTS_READY,
        catalog_entries,
    )
    from core.router import resolve
    from core.deployment import merge_tts_into_deployment, tts_service

    results = []

    def check_runtime():
        try:
            a = resolve(deployment, 'text_to_speech')
            return {'endpoint_configured': bool(a.endpoint), 'service_id': a.service_id}
        except LookupError:
            merge_tts_into_deployment(deployment)
            a = resolve(deployment, 'text_to_speech')
            return {'endpoint_configured': bool(a.endpoint), 'service_id': a.service_id, 'registered': True}

    def install_runtime():
        return {'note': 'TTS runtime install is environment-specific; graph registration only in sandbox'}

    def check_voice():
        vid = agent.get('voice_id', 'voice_001')
        p = profile_for(vid)
        return {'voice_id': p.id, 'display_name': p.display_name, 'fixture': p.fixture}

    def download_voice():
        return {'catalog': catalog_entries(), 'note': 'Fixture voices need no download; Piper voices install out-of-band'}

    def register_tts():
        merge_tts_into_deployment(deployment)
        a = resolve(deployment, 'text_to_speech')
        return {'service_id': a.service_id, 'provider': a.provider or 'test'}

    def validate_tts():
        a = resolve(deployment, 'text_to_speech')
        return {'service_id': a.service_id, 'health': 'UNKNOWN'}

    def validate_profile():
        p = profile_for(agent.get('voice_id', 'voice_001'))
        p.validate()
        return {'voice_id': p.id, 'synthesis': dict(p.synthesis)}

    def synthesize_test():
        r = synthesize_voice(deployment, agent, text, purpose='install_validate')
        return {
            'audio_id': r['audio_id'],
            'service_id': r['service_id'],
            'provider': r['provider'],
            'resolved_synthesis': r['resolved_synthesis'],
            'health': r.get('health', TTS_READY),
        }

    def assign_voice():
        return {'agent_id': agent.get('id'), 'voice_id': agent.get('voice_id', 'voice_001')}

    runners = {
        'CHECK_TTS_RUNTIME': check_runtime,
        'INSTALL_TTS_RUNTIME': install_runtime,
        'CHECK_VOICE': check_voice,
        'DOWNLOAD_VOICE': download_voice,
        'REGISTER_TTS_SERVICE': register_tts,
        'VALIDATE_TTS_SERVICE': validate_tts,
        'VALIDATE_VOICE_PROFILE': validate_profile,
        'SYNTHESIZE_TEST_AUDIO': synthesize_test,
        'ASSIGN_AGENT_VOICE': assign_voice,
    }
    for aid, label in TTS_ACTIONS:
        action = Action(aid, label)
        action.run(runners[aid])
        results.append(action)
    return results
