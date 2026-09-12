"""Deterministic speech -> memory-aware chat -> speech acceptance check."""
import io
import wave
from pathlib import Path
import tempfile
from core.stt import TestSTTProvider, normalize_wav
from core.memory import MemoryStore
from core.providers import TestProvider
from core.deployment import local_deployment
from core.agent_service import chat
from core.voice import synthesize_voice, validate_wav

def main(argv=None):
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\x01\x00' * 1600)
    with tempfile.TemporaryDirectory() as root:
        memory = MemoryStore(Path(root) / 'memory.sqlite')
        user = 'user_001'; agent = {'id':'agent_001','display_name':'Billy','voice_id':'voice_001'}
        memory.remember(user, agent['id'], "My dog's name is Cooper.")
        transcript = TestSTTProvider().transcribe(normalize_wav(audio.getvalue()))
        conversation = memory.create_conversation(user, agent['id'])
        response = chat(local_deployment(tts_provider='test'), agent, transcript.text, conversation,
                        provider=TestProvider(), memory=memory, user_id=user)
        speech = synthesize_voice(local_deployment(tts_provider='test'), agent, response['text'])
        validate_wav(speech['bytes'])
    print('STT: TestSTTProvider ->', transcript.text)
    print('LLM: TestProvider ->', response['text'])
    print('TTS: TestTTSProvider -> valid WAV')
    print('Result: ARCHITECTURE_TEST_PASS')
    print('REAL_RUNTIME_TEST_PENDING')
    return 0
if __name__ == '__main__': raise SystemExit(main())
