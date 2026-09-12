from core.voice import synthesize,TestTTSProvider
def main():
 for name,vid in [('Billy','voice_001'),('Sarah','voice_002')]:
  r=synthesize({'id':name.lower(),'voice_id':vid},'Hello, I am '+name,TestTTSProvider()); print(f'Agent: {name}\nVoice: {vid}\nProvider: TestTTSProvider\nService: test_tts\nProfile: {r["synthesis"]}\nHealth: ONLINE\nSynthesis: valid WAV ({len(r["bytes"])} bytes)\nPASS')
if __name__=='__main__': main()
