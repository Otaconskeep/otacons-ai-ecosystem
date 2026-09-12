import argparse, json
from pathlib import Path
from core.config import load
from core.topology import Deployment,Host,Service
from core.agent_service import chat
from core.providers import OllamaProvider
def main():
 p=argparse.ArgumentParser(); p.add_argument('--agent',default='Billy'); p.add_argument('--config',default=str(Path.home()/'.config/otacon/config.json')); a=p.parse_args()
 c=load(Path(a.config)); agent=next((x for x in c.get('agents',[]) if x.get('display_name','').lower()==a.agent.lower() or x.get('id')==a.agent),None)
 if not agent: print('Result: FAIL\nReason: AGENT_NOT_FOUND'); return 2
 s=c.get('llm_service',{}); svc=Service(id=s.get('id','service_llm_001'),service_type='llm',placement_resource_id=s.get('placement','host_local'),capabilities=['conversational_llm'],metadata={'endpoint':s.get('endpoint',''),'model':s.get('model','')})
 d=Deployment('deployment_local',[Host(svc.placement_resource_id)],services=[svc]); provider=OllamaProvider(s.metadata.get('endpoint',''))
 h=provider.health(s.metadata.get('model','')); print(f'Agent: {agent["display_name"]}\nProvider: Ollama\nService: {svc.id}\nModel: {s.get("model","")}\nHealth: {h.state}\nPrompt: What is your name?')
 if h.state!='ONLINE': print(f'Result: FAIL ({h.detail})'); return 1
 try: r=chat(d,agent,'What is your name?',provider=provider); print('Response: '+r['text']+'\nResult: PASS'); return 0
 except Exception as e: print(f'Result: FAIL ({e})'); return 1
if __name__=='__main__': main()
