from dataclasses import dataclass,asdict
import hashlib, wave, io, json, urllib.request, urllib.error
@dataclass
class VoiceProfile:
 id:str; display_name:str; provider:str; model:str; language:str='en-US'; synthesis:dict=None
 def __post_init__(self): self.synthesis=self.synthesis or {}
 def validate(self):
  for k,v in self.synthesis.items():
   if k in ('length_scale','noise_scale','noise_w') and (not isinstance(v,(int,float)) or v<=0): raise ValueError(f'invalid {k}')
  return True
CATALOG=(VoiceProfile('voice_001','Warm Male','test','test-voice',synthesis={'length_scale':1.0,'noise_scale':.667,'noise_w':.8}),VoiceProfile('voice_002','Measured Female','test','test-voice-2',synthesis={'length_scale':1.25,'noise_scale':.95,'noise_w':.95}))
def profile_for(i):
 p=next((x for x in CATALOG if x.id==i),None)
 if not p: raise LookupError('VOICE_NOT_INSTALLED')
 p.validate(); return p
class TTSProvider:
 def synthesize(self,text,profile,defaults=None): raise NotImplementedError
class TestTTSProvider(TTSProvider):
 def synthesize(self,text,profile,defaults=None):
  profile.validate(); b=io.BytesIO()
  with wave.open(b,'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\0\0'*800)
  return {'audio_id':hashlib.sha256((profile.id+text).encode()).hexdigest()[:12],'format':'wav','sample_rate':8000,'bytes':b.getvalue(),'voice_id':profile.id,'provider':profile.provider,'synthesis':dict(profile.synthesis)}
class PiperProvider(TTSProvider):
 def __init__(self,endpoint): self.endpoint=endpoint
 def health(self,profile=None):
  try:
   with urllib.request.urlopen(self.endpoint.rstrip('/')+'/health',timeout=5) as r: return 'ONLINE' if r.status==200 else 'DEGRADED'
  except Exception: return 'TTS_SERVICE_UNREACHABLE'
 def synthesize(self,text,profile,defaults=None):
  profile.validate(); payload={'text':text,'voice':profile.model,'language':profile.language,'settings':profile.synthesis if profile.synthesis else (defaults or {})}
  try:
   req=urllib.request.Request(self.endpoint.rstrip('/')+'/synthesize',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=120) as r: audio=r.read()
   if not audio or not audio.startswith(b'RIFF'): raise RuntimeError('malformed Piper audio')
   return {'audio_id':hashlib.sha256(audio).hexdigest()[:12],'format':'wav','sample_rate':22050,'bytes':audio,'voice_id':profile.id,'provider':'piper','synthesis':dict(profile.synthesis)}
  except urllib.error.URLError as e: raise RuntimeError(f'PROVIDER_TRANSPORT_ERROR: {e.reason}')
def provider_for(service, test_mode=False):
 if service.get('provider')=='piper': return PiperProvider(service.get('endpoint',''))
 if service.get('provider')=='test' and test_mode: return TestTTSProvider()
 raise RuntimeError('unsupported TTS provider')
def synthesize(agent,text,provider=None):
 p=profile_for(agent.get('voice_id','voice_001')); return (provider or TestTTSProvider()).synthesize(text,p)
def profile_hash(profile): return hashlib.sha256(repr(sorted(profile.synthesis.items())).encode()).hexdigest()[:12]
