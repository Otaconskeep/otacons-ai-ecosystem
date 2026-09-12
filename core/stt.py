"""Provider-neutral speech-to-text primitives."""
from __future__ import annotations
import audioop
import io
import wave
from dataclasses import dataclass

@dataclass
class Transcription:
    text: str
    language: str
    provider: str
    service_id: str
    model_id: str
    status: str = 'STT_READY'
    confidence: float | None = None
    duration_seconds: float | None = None

class STTProvider:
    provider_id = 'unknown'
    def health(self, model_id: str) -> tuple[str, str]: raise NotImplementedError
    def transcribe(self, audio: bytes, language: str | None = None) -> Transcription: raise NotImplementedError

class TestSTTProvider(STTProvider):
    provider_id = 'test'
    def health(self, model_id: str) -> tuple[str, str]: return 'STT_READY', 'deterministic test provider'
    def transcribe(self, audio: bytes, language: str | None = None) -> Transcription:
        normalized = normalize_wav(audio)
        with wave.open(io.BytesIO(normalized), 'rb') as wav:
            duration = wav.getnframes() / float(wav.getframerate() or 1)
        return Transcription("What is my dog's name?", language or 'en', self.provider_id, 'service_stt_test', 'stt_small', duration_seconds=duration)

class FasterWhisperProvider(STTProvider):
    provider_id = 'faster_whisper'
    def __init__(self, model_id: str = 'stt_small'): self.model_id = model_id
    def health(self, model_id: str | None = None) -> tuple[str, str]:
        try: import faster_whisper  # noqa: F401
        except ImportError: return 'STT_MODEL_MISSING', 'faster-whisper is not installed'
        return 'STT_MODEL_LOADING', 'model loading is not configured in this build'
    def transcribe(self, audio: bytes, language: str | None = None) -> Transcription:
        raise RuntimeError('STT_MODEL_UNAVAILABLE: configure a faster-whisper model')

CATALOG = [
 {'id':'stt_small','display_name':'Whisper Small','provider':'faster_whisper','source':'https://github.com/SYSTRAN/faster-whisper','license':'MIT','storage_gb':0.5,'ram_gb':4,'vram_gb':2,'cpu_supported':True,'gpu_supported':True,'speed_tier':'fast','quality_tier':'balanced','languages':'multilingual'},
 {'id':'stt_balanced','display_name':'Whisper Medium','provider':'faster_whisper','source':'https://github.com/SYSTRAN/faster-whisper','license':'MIT','storage_gb':1.5,'ram_gb':8,'vram_gb':6,'cpu_supported':True,'gpu_supported':True,'speed_tier':'moderate','quality_tier':'high','languages':'multilingual'},
]
def recommend(hardware) -> dict:
    status = ((getattr(hardware, 'gpu_detection', None) or {}).get('status') if hardware is not None else None)
    return CATALOG[1] if status == 'detected' and getattr(hardware, 'gpus', []) else CATALOG[0]
def normalize_wav(data: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(data), 'rb') as source:
            if source.getsampwidth() != 2 or source.getcomptype() != 'NONE': raise ValueError('AUDIO_INVALID: expected PCM16 WAV')
            channels, rate, frames = source.getnchannels(), source.getframerate(), source.readframes(source.getnframes())
        if not frames: raise ValueError('NO_SPEECH_DETECTED')
        if channels > 1: frames = audioop.tomono(frames, 2, 0.5, 0.5)
        if rate != 16000: frames, _ = audioop.ratecv(frames, 2, 1, rate, 16000, None)
        out = io.BytesIO()
        with wave.open(out, 'wb') as target:
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(16000); target.writeframes(frames)
        return out.getvalue()
    except ValueError: raise
    except Exception as exc: raise ValueError('AUDIO_INVALID') from exc
