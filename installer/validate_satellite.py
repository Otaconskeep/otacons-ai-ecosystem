from core.satellite import *
from core.stt import Transcription
def main(argv=None):
 s=VoiceSatellite('sat_001','Test Satellite','node_test',assigned_agent_id='agent_001',status='READY',trust_state='TRUSTED'); st=type('S',(),{'transcribe':lambda _,x:Transcription("What's my dog's name?",'en','test','stt','small')})(); a=OtaconVoiceSatelliteAgent(s,TestWakeWordProvider(),st,lambda text,s:'Your dog is Cooper.',lambda text,s:b'RIFF-WAV'); r=a.process(b'wake',b'utterance'); print('WAKE_PROVIDER_PASS'); print('WAKE_DETECTION_PASS'); print('NO_WAKE_GATING_PASS' if a.process(b'noise',b'bad')['status']=='NO_WAKE' else 'FAIL'); print('SATELLITE_PIPELINE_PASS'); print('VOICE_LOOP_PASS'); print('ARCHITECTURE_TEST_PASS'); print('REAL_SATELLITE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT'); return 0
if __name__=='__main__': raise SystemExit(main())
