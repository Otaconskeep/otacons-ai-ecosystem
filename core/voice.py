"""Provider-neutral TTS: VoiceProfile catalog, synthesis precedence, shared synthesize_voice path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import io
import os
import time
import wave

from core.router import resolve
from core.wyoming_transport import (
    WyomingTransportError,
    wyoming_health,
    wyoming_synthesize,
)

# ---------------------------------------------------------------------------
# Structured health / readiness codes
# ---------------------------------------------------------------------------
TTS_READY = 'TTS_READY'
TTS_SERVICE_UNREACHABLE = 'TTS_SERVICE_UNREACHABLE'
TTS_SERVICE_UNHEALTHY = 'TTS_SERVICE_UNHEALTHY'
VOICE_NOT_INSTALLED = 'VOICE_NOT_INSTALLED'
VOICE_NOT_AVAILABLE = 'VOICE_NOT_AVAILABLE'
VOICE_PROFILE_INVALID = 'VOICE_PROFILE_INVALID'
SYNTHESIS_FAILED = 'SYNTHESIS_FAILED'
PROVIDER_TRANSPORT_ERROR = 'PROVIDER_TRANSPORT_ERROR'

CATALOG_AVAILABLE = 'CATALOG_AVAILABLE'
INSTALLED = 'INSTALLED'
READY = 'READY'

PROVIDER_DEFAULTS = {'length_scale': 1.0, 'noise_scale': 0.667, 'noise_w': 0.8}


class TTSError(RuntimeError):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def as_dict(self) -> dict[str, Any]:
        return {'code': self.code, 'message': self.message, **self.extra}


@dataclass
class VoiceProfile:
    id: str
    display_name: str
    provider: str
    model: str
    language: str = 'en-US'
    synthesis: dict | None = None
    speaker: str | None = None
    # Catalog metadata (licensing / fixture marking)
    license: str = ''
    source: str = ''
    fixture: bool = False
    status_hint: str = CATALOG_AVAILABLE

    def __post_init__(self):
        self.synthesis = dict(self.synthesis or {})

    def validate(self):
        for k, v in self.synthesis.items():
            if k in ('length_scale', 'noise_scale', 'noise_w') and (not isinstance(v, (int, float)) or v <= 0):
                raise ValueError(f'invalid {k}')
        return True


# Public catalog. Production voices map to Piper models. voice_001/002 keep stable
# IDs so existing agents/UI selections keep working; they are NOT silent fixtures.
CATALOG: tuple[VoiceProfile, ...] = (
    VoiceProfile(
        'voice_001',
        'Warm Male',
        'piper',
        'en_US-bryce-medium',
        language='en-US',
        synthesis={'length_scale': 1.0, 'noise_scale': 0.667, 'noise_w': 0.8},
        license='MIT (Piper / rhasspy voice models — see upstream voice LICENSE)',
        source='https://github.com/rhasspy/piper',
        fixture=False,
        status_hint=CATALOG_AVAILABLE,
    ),
    VoiceProfile(
        'voice_002',
        'Measured Female',
        'piper',
        'en_US-hfc_female-medium',
        language='en-US',
        synthesis={'length_scale': 1.25, 'noise_scale': 0.95, 'noise_w': 0.95},
        license='MIT (Piper / rhasspy voice models — see upstream voice LICENSE)',
        source='https://github.com/rhasspy/piper',
        fixture=False,
        status_hint=CATALOG_AVAILABLE,
    ),
    VoiceProfile(
        'en_US-lessac-medium',
        'Lessac (US English, medium)',
        'piper',
        'en_US-lessac-medium',
        language='en-US',
        synthesis={},
        license='MIT (Piper / rhasspy voice models — see upstream voice LICENSE)',
        source='https://github.com/rhasspy/piper',
        fixture=False,
        status_hint=CATALOG_AVAILABLE,
    ),
    # Explicit test-only fixtures (hidden from UI unless OTACON_SHOW_TEST_VOICES=1)
    VoiceProfile(
        'test_voice_warm',
        'Warm Male (test fixture)',
        'test',
        'test-voice',
        synthesis={'length_scale': 1.0, 'noise_scale': 0.667, 'noise_w': 0.8},
        license='TEST FIXTURE — not a redistributable production Piper voice',
        source='otacon-public synthetic test fixture',
        fixture=True,
        status_hint=CATALOG_AVAILABLE,
    ),
    VoiceProfile(
        'test_voice_measured',
        'Measured Female (test fixture)',
        'test',
        'test-voice-2',
        synthesis={'length_scale': 1.25, 'noise_scale': 0.95, 'noise_w': 0.95},
        license='TEST FIXTURE — not a redistributable production Piper voice',
        source='otacon-public synthetic test fixture',
        fixture=True,
        status_hint=CATALOG_AVAILABLE,
    ),
)


def catalog_entries() -> list[dict[str, Any]]:
    show_fixtures = os.getenv('OTACON_SHOW_TEST_VOICES', '').lower() in ('1', 'true', 'yes')
    out = []
    for p in CATALOG:
        if p.fixture and not show_fixtures:
            continue
        out.append({
            'id': p.id,
            'display_name': p.display_name,
            'provider': p.provider,
            'language': p.language,
            'fixture': p.fixture,
            'license': p.license,
            'source': p.source,
            'friendly_name': p.display_name,
            'model': p.model,
        })
    return out


def profile_for(i: str) -> VoiceProfile:
    p = next((x for x in CATALOG if x.id == i), None)
    if not p:
        raise LookupError(VOICE_NOT_INSTALLED)
    try:
        p.validate()
    except ValueError as e:
        raise TTSError(VOICE_PROFILE_INVALID, str(e)) from e
    return p


def profile_hash(profile: VoiceProfile) -> str:
    payload = {
        'id': profile.id,
        'provider': profile.provider,
        'model': profile.model,
        'speaker': profile.speaker,
        'synthesis': sorted((profile.synthesis or {}).items()),
    }
    return hashlib.sha256(repr(payload).encode()).hexdigest()[:12]


def resolve_synthesis_settings(
    profile: VoiceProfile,
    production_override: dict | None = None,
    service_defaults: dict | None = None,
    provider_defaults: dict | None = None,
) -> dict[str, float]:
    """Precedence (permanent):
    1. explicit per-voice production override
    2. validated VoiceProfile synthesis settings
    3. TTS service defaults
    4. provider built-in defaults
    """
    out = dict(provider_defaults or PROVIDER_DEFAULTS)
    if service_defaults:
        out.update({k: v for k, v in service_defaults.items() if v is not None})
    if profile.synthesis:
        # Only explicit keys on the profile overwrite service defaults
        out.update({k: v for k, v in profile.synthesis.items() if v is not None})
    if production_override:
        out.update({k: v for k, v in production_override.items() if v is not None})
    # Validate resolved numeric profile
    tmp = VoiceProfile(profile.id, profile.display_name, profile.provider, profile.model, synthesis=dict(out))
    tmp.validate()
    return {k: float(out[k]) for k in ('length_scale', 'noise_scale', 'noise_w') if k in out}


class TTSProvider:
    def synthesize(self, text, profile, defaults=None, production_override=None):
        raise NotImplementedError

    def health(self, profile=None):
        return TTS_READY


class TestTTSProvider(TTSProvider):
    """Deterministic synthetic WAV provider for architecture / sandbox tests."""

    def health(self, profile=None):
        return TTS_READY

    def synthesize(self, text, profile, defaults=None, production_override=None):
        profile.validate()
        settings = resolve_synthesis_settings(profile, production_override, defaults)
        # Encode settings faintly into PCM amplitude so isolation remains audible in hashes
        scale = int(max(1, min(200, settings.get('length_scale', 1.0) * 80)))
        raw = bytearray()
        for i in range(800):
            raw.append((scale + (i % 7)) % 256)
            raw.append(0)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(bytes(raw))
        audio = buf.getvalue()
        return {
            'audio_id': hashlib.sha256((profile.id + text + repr(sorted(settings.items()))).encode()).hexdigest()[:12],
            'format': 'wav',
            'sample_rate': 8000,
            'duration_sec': 800 / 8000,
            'bytes': audio,
            'voice_id': profile.id,
            'provider': 'test',
            'synthesis': settings,
        }


class FailingTTSProvider(TTSProvider):
    """Forces synthesis failure for chat-survival tests."""

    def health(self, profile=None):
        return TTS_READY

    def synthesize(self, text, profile, defaults=None, production_override=None):
        raise TTSError(SYNTHESIS_FAILED, 'forced TTS failure for tests')


class PiperProvider(TTSProvider):
    """Production Piper provider. Transport details stay in wyoming_transport."""

    def __init__(self, endpoint: str, timeout: float = 120.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def health(self, profile=None):
        try:
            return wyoming_health(self.endpoint, timeout=min(5.0, self.timeout))
        except WyomingTransportError as e:
            return e.code if e.code in (TTS_SERVICE_UNREACHABLE, TTS_SERVICE_UNHEALTHY) else TTS_SERVICE_UNREACHABLE

    def synthesize(self, text, profile, defaults=None, production_override=None):
        try:
            profile.validate()
        except ValueError as e:
            raise TTSError(VOICE_PROFILE_INVALID, str(e)) from e
        settings = resolve_synthesis_settings(profile, production_override, defaults)
        voice_name = profile.model or profile.id
        try:
            result = wyoming_synthesize(
                self.endpoint,
                text=text,
                voice_name=voice_name,
                speaker=profile.speaker,
                settings=settings,
                timeout=self.timeout,
            )
        except WyomingTransportError as e:
            raise TTSError(e.code, e.message) from e
        except Exception as e:
            raise TTSError(PROVIDER_TRANSPORT_ERROR, str(e)) from e

        pcm = result['pcm']
        rate = result['sample_rate']
        width = result['sample_width']
        channels = result['channels']
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(pcm)
        audio = buf.getvalue()
        if not audio or not audio.startswith(b'RIFF'):
            raise TTSError(SYNTHESIS_FAILED, 'malformed Piper WAV')
        duration = (len(pcm) / max(1, width * channels)) / max(1, rate)
        return {
            'audio_id': hashlib.sha256(audio).hexdigest()[:12],
            'format': 'wav',
            'sample_rate': rate,
            'duration_sec': duration,
            'bytes': audio,
            'voice_id': profile.id,
            'provider': 'piper',
            'synthesis': settings,
        }


def provider_for_assignment(assignment, provider: TTSProvider | None = None) -> TTSProvider:
    if provider is not None:
        return provider
    endpoint = getattr(assignment, 'endpoint', '') or ''
    provider_name = (getattr(assignment, 'provider', None) or '').strip().lower()
    if not provider_name:
        if endpoint.startswith('test://') or os.getenv('OTACON_TTS_PROVIDER', '').lower() == 'test':
            provider_name = 'test'
        else:
            provider_name = 'piper'
    if provider_name == 'test':
        return TestTTSProvider()
    if not endpoint or 'tts-service-redacted' in endpoint:
        raise TTSError(TTS_SERVICE_UNREACHABLE, 'TTS service endpoint is not configured')
    return PiperProvider(endpoint)


def default_cache_dir() -> Path:
    override = os.getenv('OTACON_TTS_CACHE')
    if override:
        return Path(override)
    return Path.home() / '.config' / 'otacon' / 'runtime' / 'tts-cache'


def _prune_cache(cache_dir: Path, max_files: int = 64, max_age_sec: int = 7 * 24 * 3600) -> None:
    if not cache_dir.is_dir():
        return
    files = sorted(cache_dir.glob('*.wav'), key=lambda p: p.stat().st_mtime)
    now = time.time()
    kept = []
    for f in files:
        try:
            age = now - f.stat().st_mtime
            if age > max_age_sec:
                f.unlink(missing_ok=True)
            else:
                kept.append(f)
        except OSError:
            pass
    while len(kept) > max_files:
        old = kept.pop(0)
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def store_audio(audio_bytes: bytes, audio_id: str, cache_dir: Path | None = None) -> str:
    cache_dir = Path(cache_dir or default_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f'{audio_id}.wav'
    path.write_bytes(audio_bytes)
    _prune_cache(cache_dir)
    return str(path)


def validate_wav(audio_bytes: bytes) -> dict[str, Any]:
    if not audio_bytes or not audio_bytes.startswith(b'RIFF'):
        raise TTSError(SYNTHESIS_FAILED, 'audio is not a valid WAV (RIFF)')
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        if frames <= 0:
            raise TTSError(SYNTHESIS_FAILED, 'WAV has zero frames')
        return {
            'sample_rate': rate,
            'channels': w.getnchannels(),
            'sample_width': w.getsampwidth(),
            'frames': frames,
            'duration_sec': frames / max(1, rate),
        }


def assert_audible_speech(
    audio_bytes: bytes,
    *,
    min_duration_sec: float = 0.35,
    min_peak: int = 500,
) -> dict[str, Any]:
    """Reject empty / near-silent / sub-syllable placeholders (the old TestTTS beep)."""
    meta = validate_wav(audio_bytes)
    if meta['duration_sec'] < min_duration_sec:
        raise TTSError(
            SYNTHESIS_FAILED,
            f'audio too short to be spoken speech ({meta["duration_sec"]:.2f}s < {min_duration_sec}s)',
        )
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        pcm = w.readframes(w.getnframes())
        width = w.getsampwidth()
    peak = 0
    if width == 2 and pcm:
        import array
        samples = array.array('h')
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        peak = max((abs(s) for s in samples), default=0)
    elif pcm:
        peak = max(pcm)
    if peak < min_peak:
        raise TTSError(
            SYNTHESIS_FAILED,
            f'audio is near-silent (peak={peak} < {min_peak}) — not spoken speech',
        )
    return {**meta, 'peak': peak}


def _tts_preview_log(message: str) -> None:
    print(f'[TTS PREVIEW] {message}', flush=True)


def _allow_test_tts() -> bool:
    return os.getenv('OTACON_ALLOW_TEST_TTS', '').lower() in ('1', 'true', 'yes')


def voice_status(voice_id: str, *, model_installed: bool | None = None, tts_health: str | None = None, synthesis_ok: bool | None = None) -> str:
    """CATALOG_AVAILABLE < INSTALLED < READY. READY requires successful synthesis path."""
    try:
        profile_for(voice_id)
    except LookupError:
        return VOICE_NOT_AVAILABLE
    except TTSError:
        return VOICE_PROFILE_INVALID
    if synthesis_ok:
        return READY
    if model_installed and tts_health == TTS_READY:
        return INSTALLED
    if model_installed:
        return INSTALLED
    return CATALOG_AVAILABLE


def synthesize(agent, text, provider=None):
    """Backward-compatible helper used by existing isolation tests (TestTTSProvider default)."""
    p = profile_for(agent.get('voice_id', 'voice_001'))
    return (provider or TestTTSProvider()).synthesize(text, p)


def _assignment_service_defaults(assignment) -> dict:
    defaults = getattr(assignment, 'defaults', None)
    if isinstance(defaults, dict):
        return dict(defaults)
    return {}


def synthesize_voice(
    deployment,
    agent: dict,
    text: str,
    *,
    provider: TTSProvider | None = None,
    production_override: dict | None = None,
    cache_dir: Path | None = None,
    purpose: str = 'production',
) -> dict[str, Any]:
    """Single shared synthesis path for Voice Preview and production speech.

    VoiceProfile → capability router → registered TTS service → provider → resolved settings → audio
    """
    is_preview = purpose == 'preview'
    agent_name = agent.get('display_name') or agent.get('id') or 'agent'
    voice_id = agent.get('voice_id') or 'voice_001'
    if is_preview:
        _tts_preview_log(f'requested agent={agent_name} voice={voice_id}')

    if not (text or '').strip():
        raise TTSError(SYNTHESIS_FAILED, 'text is empty')
    try:
        profile = profile_for(voice_id)
    except LookupError as e:
        raise TTSError(VOICE_NOT_INSTALLED, f'voice not installed: {voice_id}') from e

    try:
        assignment = resolve(deployment, 'text_to_speech')
    except LookupError as e:
        raise TTSError(TTS_SERVICE_UNREACHABLE, 'no TTS service provides text_to_speech') from e

    service_defaults = _assignment_service_defaults(assignment)
    # Allow metadata on Service via monkey-patched attributes from builders
    meta_defaults = getattr(assignment, 'service_defaults', None)
    if isinstance(meta_defaults, dict):
        service_defaults = {**meta_defaults, **service_defaults}

    tts = provider_for_assignment(assignment, provider)
    backend = type(tts).__name__
    if is_preview:
        _tts_preview_log(f'backend={backend} model={profile.model} provider_profile={profile.provider}')

    health = tts.health(profile)
    if health not in (TTS_READY, 'ONLINE'):
        # Test provider returns TTS_READY; Piper may return unreachable before synthesize
        if health == TTS_SERVICE_UNREACHABLE:
            raise TTSError(TTS_SERVICE_UNREACHABLE, 'TTS service unreachable')
        if health == TTS_SERVICE_UNHEALTHY:
            raise TTSError(TTS_SERVICE_UNHEALTHY, 'TTS service unhealthy')

    if isinstance(tts, TestTTSProvider) and not _allow_test_tts():
        raise TTSError(
            SYNTHESIS_FAILED,
            'TTS is still on the silent test double (produces a faint beep, not speech). '
            'Piper is not configured. Re-run OtaconsKeep Setup, or set '
            'OTACON_TTS_PROVIDER=piper and OTACON_TTS_ENDPOINT=wyoming://127.0.0.1:10200.',
        )

    if is_preview:
        _tts_preview_log('synthesis start')
    try:
        raw = tts.synthesize(text, profile, defaults=service_defaults, production_override=production_override)
    except TTSError:
        raise
    except Exception as e:
        raise TTSError(SYNTHESIS_FAILED, str(e)) from e

    audio = raw['bytes']
    wav_meta = validate_wav(audio)
    # User-facing preview/production must be real speech — not the 0.1s near-silent test beep.
    if purpose in ('preview', 'production') and not _allow_test_tts():
        audible = assert_audible_speech(audio)
        wav_meta = {**wav_meta, **audible}
    path = store_audio(audio, raw['audio_id'], cache_dir=cache_dir)
    resolved = raw.get('synthesis') or resolve_synthesis_settings(profile, production_override, service_defaults)
    ph = profile_hash(profile)
    if is_preview:
        _tts_preview_log(
            f'synthesis PASS bytes={len(audio)} format={raw.get("format", "wav")} '
            f'duration={wav_meta["duration_sec"]:.3f} peak={wav_meta.get("peak", "?")}'
        )
    result = {
        'status': READY,
        'audio_id': raw['audio_id'],
        'audio_path': path,
        'format': raw.get('format', 'wav'),
        'sample_rate': raw.get('sample_rate') or wav_meta['sample_rate'],
        'duration_sec': raw.get('duration_sec') or wav_meta['duration_sec'],
        'bytes': audio,
        'byte_count': len(audio),
        'peak': wav_meta.get('peak'),
        'voice_id': profile.id,
        'provider': raw.get('provider') or profile.provider,
        'service_id': assignment.service_id,
        'agent_id': agent.get('id'),
        'profile_id': ph,
        'profile_version': ph,
        'resolved_synthesis': resolved,
        'synthesis': resolved,
        'purpose': purpose,
        'health': health if health != 'ONLINE' else TTS_READY,
        'trace': {
            'agent_id': agent.get('id'),
            'voice_id': profile.id,
            'provider': raw.get('provider') or profile.provider,
            'service_id': assignment.service_id,
            'resolved_synthesis': resolved,
            'profile_hash': ph,
            'purpose': purpose,
            'byte_count': len(audio),
            'duration_sec': wav_meta['duration_sec'],
            'peak': wav_meta.get('peak'),
        },
    }
    return result


def public_result(result: dict[str, Any], include_audio_b64: bool = False) -> dict[str, Any]:
    """API-facing subset (optionally with base64 audio)."""
    import base64
    out = {
        'status': result.get('status'),
        'audio_path': result.get('audio_path'),
        'audio_id': result.get('audio_id'),
        'format': result.get('format'),
        'sample_rate': result.get('sample_rate'),
        'duration_sec': result.get('duration_sec'),
        'byte_count': result.get('byte_count'),
        'peak': result.get('peak'),
        'voice_id': result.get('voice_id'),
        'provider': result.get('provider'),
        'service_id': result.get('service_id'),
        'agent_id': result.get('agent_id'),
        'profile_id': result.get('profile_id'),
        'resolved_synthesis': result.get('resolved_synthesis'),
        'health': result.get('health'),
        'trace': result.get('trace'),
    }
    if include_audio_b64 and result.get('bytes'):
        out['audio_base64'] = base64.b64encode(result['bytes']).decode('ascii')
    return out
