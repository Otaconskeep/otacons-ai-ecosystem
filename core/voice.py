from dataclasses import dataclass,asdict
import hashlib, wave, io
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
 def health(self): return 'UNKNOWN'
 def synthesize(self,text,profile,defaults=None): raise RuntimeError('Piper transport not configured')
def synthesize(agent,text,provider=None):
 p=profile_for(agent.get('voice_id','voice_001')); return (provider or TestTTSProvider()).synthesize(text,p)
def profile_hash(profile): return hashlib.sha256(repr(sorted(profile.synthesis.items())).encode()).hexdigest()[:12]
