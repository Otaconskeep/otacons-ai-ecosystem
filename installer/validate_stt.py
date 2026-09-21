"""STT validation — TestSTT is deterministic only; real STT must prove model load."""
from __future__ import annotations

import argparse
import io
import wave

from core.stt import FasterWhisperProvider, TestSTTProvider, normalize_wav


def fixture_wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b'\x01\x00' * 1600)
    return out.getvalue()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--real', action='store_true', help='Require real Faster-Whisper readiness')
    args = p.parse_args(argv)

    audio = normalize_wav(fixture_wav())
    test = TestSTTProvider().transcribe(audio)
    print('Provider: test')
    print('Transcript:', test.text)
    print('Result: TEST_STT_PASS')

    fw = FasterWhisperProvider()
    state, detail = fw.health()
    print(f'Real STT health: {state} ({detail})')

    if not args.real:
        print('REAL_STT_ACCEPTANCE_PENDING (pass --real to require production STT)')
        return 0

    if state != 'STT_READY':
        # Installing the Python package alone is not enough.
        print('Result: FAIL — STT not READY (package/model lifecycle incomplete)')
        return 1
    try:
        result = fw.transcribe(audio)
        # Silence/near-silence fixtures often yield empty text; that is OK as long as
        # WhisperModel loaded and transcribe() completed without raising.
        print('Transcript(real):', repr(result.text))
        print('Result: REAL_STT_PASS')
        return 0
    except Exception as exc:
        print(f'Result: FAIL — {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
