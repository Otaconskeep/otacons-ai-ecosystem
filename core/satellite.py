from dataclasses import dataclass
from datetime import datetime, timezone
class WakeWordProvider:
 def health(self): raise NotImplementedError
 def detect(self,audio): raise NotImplementedError
class TestWakeWordProvider(WakeWordProvider):
 def health(self): return 'READY'
 def detect(self,audio): return bool(audio and audio==b'wake')
class LocalWakeWordProvider(WakeWordProvider):
 def health(self): return 'UNAVAILABLE'
 def detect(self,audio): raise RuntimeError('WAKE_MODEL_UNAVAILABLE')
@dataclass
class VoiceSatellite:
 satellite_id:str; display_name:str; node_id:str; room_label:str|None=None; status:str='UNPAIRED'; trust_state:str='UNPAIRED'; microphone_capable:bool=True; speaker_capable:bool=True; wake_word_capable:bool=True; assigned_agent_id:str='agent_001'; user_id:str='local_user'; wake_profile_id:str='wake_default'; muted:bool=False; last_seen:str|None=None
class SatellitePlayback:
 def play(self,audio): return bool(audio)
 def stop(self): return True
class OtaconVoiceSatelliteAgent:
 def __init__(self,satellite,wake,stt,chat_fn,tts_fn,playback=None): self.satellite=satellite; self.wake=wake; self.stt=stt; self.chat_fn=chat_fn; self.tts_fn=tts_fn; self.playback=playback or SatellitePlayback()
 def heartbeat(self): self.satellite.last_seen=datetime.now(timezone.utc).isoformat(); return {'satellite_id':self.satellite.satellite_id,'status':self.satellite.status,'muted':self.satellite.muted}
 def process(self,wake_audio,utterance):
  if self.satellite.muted:return {'status':'MUTED'}
  if not self.wake.detect(wake_audio):return {'status':'NO_WAKE'}
  self.satellite.status='TRANSCRIBING'; transcript=self.stt.transcribe(utterance)
  if not transcript.text.strip(): self.satellite.status='LISTENING_FOR_WAKE_WORD'; return {'status':'NO_SPEECH_DETECTED'}
  self.satellite.status='THINKING'; response=self.chat_fn(transcript.text,self.satellite); self.satellite.status='SPEAKING'; self.playback.play(self.tts_fn(response,self.satellite)); self.satellite.status='LISTENING_FOR_WAKE_WORD'; return {'status':'VOICE_LOOP_PASS','transcript':transcript.text,'response':response}
