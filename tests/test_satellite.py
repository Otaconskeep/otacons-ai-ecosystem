import unittest
from core.satellite import *
class SatelliteTests(unittest.TestCase):
 def test_wake_gating_and_mute(self):
  s=VoiceSatellite('s','Kitchen','n',status='READY',trust_state='TRUSTED'); self.assertFalse(TestWakeWordProvider().detect(b'noise')); s.muted=True; self.assertEqual(OtaconVoiceSatelliteAgent(s,TestWakeWordProvider(),None,None,None).process(b'wake',b'x')['status'],'MUTED')
 def test_identity_and_heartbeat(self):
  s=VoiceSatellite('s','Office','n'); self.assertEqual(s.assigned_agent_id,'agent_001'); self.assertEqual(OtaconVoiceSatelliteAgent(s,TestWakeWordProvider(),None,None,None).heartbeat()['satellite_id'],'s')
 def test_provider_boundary(self): self.assertEqual(LocalWakeWordProvider().health(),'UNAVAILABLE')
 def test_pipeline_state(self):
  from core.stt import Transcription
  s=VoiceSatellite('s','Test','n',status='READY',trust_state='TRUSTED'); st=type('S',(),{'transcribe':lambda _,x:Transcription('hello','en','test','s','m')})(); a=OtaconVoiceSatelliteAgent(s,TestWakeWordProvider(),st,lambda text,s:'ok',lambda text,s:b'a'); self.assertEqual(a.process(b'wake',b'a')['status'],'VOICE_LOOP_PASS'); self.assertEqual(s.status,'LISTENING_FOR_WAKE_WORD')
if __name__=='__main__': unittest.main()
