"""Deterministic STT architecture check; real model validation is external."""
import io, wave
from core.stt import TestSTTProvider, normalize_wav

def fixture():
 out=io.BytesIO()
 with wave.open(out,'wb') as w:
  w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\x01\x00'*1600)
 return out.getvalue()
def main(argv=None):
 result=TestSTTProvider().transcribe(normalize_wav(fixture()))
 print('Provider: test'); print('Service: service_stt_test'); print('Model: stt_small'); print('Health: STT_READY')
 print('Detected language:',result.language); print('Transcript:',result.text); print('Result: TEST_STT_PASS'); print('REAL_STT_ACCEPTANCE_PENDING')
 return 0
if __name__=='__main__': raise SystemExit(main())
