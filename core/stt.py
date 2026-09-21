"""Provider-neutral speech-to-text primitives."""
from __future__ import annotations

import audioop
import io
import os
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

# Catalog id -> CTranslate2/faster-whisper model size on Hugging Face.
_FW_MODEL_MAP = {
    'stt_small': 'base',
    'stt_balanced': 'small',
    'tiny': 'tiny',
    'base': 'base',
    'small': 'small',
    'medium': 'medium',
}
_FW_CACHE: dict[str, object] = {}


def _fw_size(model_id: str) -> str:
    mid = (model_id or 'stt_small').strip()
    return _FW_MODEL_MAP.get(mid, _FW_MODEL_MAP.get(mid.lower(), 'base'))


class FasterWhisperProvider(STTProvider):
    provider_id = 'faster_whisper'

    def __init__(self, model_id: str = 'stt_small'):
        self.model_id = model_id or 'stt_small'

    def _load(self):
        size = _fw_size(self.model_id)
        if size in _FW_CACHE:
            return _FW_CACHE[size]
        from faster_whisper import WhisperModel  # type: ignore
        device = (os.environ.get('OTACON_STT_DEVICE') or 'cpu').strip() or 'cpu'
        compute = (os.environ.get('OTACON_STT_COMPUTE_TYPE') or 'int8').strip() or 'int8'
        model = WhisperModel(size, device=device, compute_type=compute)
        _FW_CACHE[size] = model
        return model

    def health(self, model_id: str | None = None) -> tuple[str, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return 'STT_MODEL_MISSING', 'faster-whisper is not installed'
        try:
            mid = model_id or self.model_id
            size = _fw_size(mid)
            self.model_id = mid
            self._load()
            return 'STT_READY', f'faster-whisper model={size} cached'
        except Exception as exc:  # noqa: BLE001 — surface load errors to installer
            return 'STT_MODEL_LOADING', f'model load failed: {type(exc).__name__}: {exc}'[:200]

    def transcribe(self, audio: bytes, language: str | None = None) -> Transcription:
        state, detail = self.health()
        if state != 'STT_READY':
            raise RuntimeError(f'STT_MODEL_UNAVAILABLE: {detail}')
        normalized = normalize_wav(audio)
        # Write temp path-less: faster-whisper accepts file path or ndarray; use BytesIO via temp file.
        import tempfile
        from pathlib import Path
        model = self._load()
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(normalized)
            path = tmp.name
        try:
            segments, info = model.transcribe(
                path,
                language=(language or None),
                beam_size=1,
                vad_filter=False,
            )
            parts = [getattr(seg, 'text', '') or '' for seg in segments]
            text = ' '.join(p.strip() for p in parts if p and p.strip()).strip()
            lang = getattr(info, 'language', None) or (language or 'en')
            dur = getattr(info, 'duration', None)
            return Transcription(
                text or '',
                str(lang),
                self.provider_id,
                'service_stt_001',
                self.model_id,
                status='STT_READY',
                duration_seconds=float(dur) if dur is not None else None,
            )
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

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
