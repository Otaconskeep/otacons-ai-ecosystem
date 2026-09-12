import io, wave, unittest
from types import SimpleNamespace
from core.stt import TestSTTProvider, FasterWhisperProvider, normalize_wav, recommend
from core.topology import Deployment, Host, Service
from core.router import resolve

def wav(rate=8000, channels=2, frames=b'\x01\x00'*80):
 b=io.BytesIO()
 with wave.open(b,'wb') as w:
  w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate); w.writeframes(frames)
 return b.getvalue()
class STTTests(unittest.TestCase):
 def test_provider_and_normalization(self):
  out=normalize_wav(wav());
  with wave.open(io.BytesIO(out),'rb') as w: self.assertEqual((w.getnchannels(),w.getframerate(),w.getsampwidth()),(1,16000,2))
  r=TestSTTProvider().transcribe(out); self.assertIn('dog',r.text); self.assertEqual(r.status,'STT_READY')
 def test_invalid_and_empty_audio(self):
  with self.assertRaises(ValueError): normalize_wav(b'bad')
  with self.assertRaises(ValueError): normalize_wav(wav(frames=b''))
 def test_router_uses_registered_stt_service(self):
  d=Deployment('d',[Host('host')],services=[Service(id='service_stt_001',service_type='stt',placement_resource_id='host',capabilities=['speech_to_text'],metadata={'provider':'faster_whisper','model':'stt_small','endpoint':'local://stt'})])
  a=resolve(d,'speech_to_text'); self.assertEqual((a.service_id,a.provider,a.model),('service_stt_001','faster_whisper','stt_small'))
 def test_gpu_error_uses_cpu_safe_catalog(self):
  self.assertEqual(recommend(SimpleNamespace(gpu_detection={'status':'error'},gpus=[]))['id'],'stt_small')
 def test_production_provider_does_not_fallback(self):
  self.assertNotEqual(FasterWhisperProvider().provider_id, TestSTTProvider.provider_id)
if __name__=='__main__': unittest.main()

class VoiceLoopTests(unittest.TestCase):
 def test_stt_chat_memory_tts_path(self):
  import tempfile
  from pathlib import Path
  from core.memory import MemoryStore
  from core.agent_service import chat
  from core.voice import synthesize_voice, validate_wav
  from core.providers import TestProvider
  from core.deployment import local_deployment
  with tempfile.TemporaryDirectory() as d:
   mem=MemoryStore(Path(d)/'memory.sqlite'); uid='user_001'; agent={'id':'agent_001','display_name':'Billy','voice_id':'voice_001'}
   cid=mem.create_conversation(uid,agent['id']); mem.remember(uid,agent['id'],"My dog's name is Cooper.")
   transcript=TestSTTProvider().transcribe(normalize_wav(wav())).text
   result=chat(local_deployment(tts_provider='test'),agent,transcript,cid,provider=TestProvider(),memory=mem,user_id=uid)
   self.assertEqual(result['text'],"Your dog's name is Cooper.")
   audio=synthesize_voice(local_deployment(tts_provider='test'),agent,result['text'])
   validate_wav(audio['bytes']); self.assertEqual(audio['voice_id'],'voice_001')
