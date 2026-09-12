from http.server import BaseHTTPRequestHandler,HTTPServer
import json,os,base64
from pathlib import Path
from core.platform import detect
from core.planner import recommend_hardware_plan
from core.config import build_config,save
from core.storage import volumes,recommended_volume
from core.topology import Deployment,Host,Service
from core.agent_service import chat
from core.providers import TestProvider
from core.voice import synthesize,TestTTSProvider,profile_hash,profile_for
from core.memory import MemoryStore
MEMORY=MemoryStore(Path.home()/'.config/otacon/runtime/memory.sqlite')
class Handler(BaseHTTPRequestHandler):
 def send_json(self,data,status=200):
  b=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  if self.path=='/api/scan':
   h=detect(); self.send_json({'hardware':recommend_hardware_plan(h),'storage':volumes()})
  elif self.path=='/api/branding': self.send_json({'product_name':'Otacon','tagline':'Local AI Command System','creator':'Antonio Garcia','show_creator_credit':True})
  elif self.path=='/': self.path='/index.html'; self.serve()
  else: self.serve()
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(n) or '{}')
  if self.path=='/api/plan':
   h=detect(); st=data.get('storage') or recommended_volume(); self.send_json({'config':build_config(recommend_hardware_plan(h),data.get('name','Assistant'),data.get('features',[]),storage=st),'storage':st})
  elif self.path=='/api/save':
   root=Path(data.get('output') or (Path.home()/'.config/otacon')); self.send_json({'path':str(save(data['config'],root))})
  elif self.path=='/api/load_configuration':
   p=Path.home()/'.config/otacon/config.json'; self.send_json(json.loads(p.read_text()) if p.is_file() else {})
  elif self.path=='/api/chat_with_agent':
   agent=data.get('agent',{'id':data.get('agent_id','agent_001'),'display_name':data.get('display_name','Billy')})
   svc=Service(id='service_llm_test',service_type='llm',placement_resource_id='host_local',capabilities=['conversational_llm'],metadata={'endpoint':'test://','model':'chat_small'})
   d=Deployment('deployment_local',[Host('host_local')],services=[svc])
   cid=data.get('conversation_id') or MEMORY.create_conversation(data.get('user_id','local_user'),agent['id'])
   try:
    result=chat(d,agent,data.get('message',''),cid,provider=TestProvider(),memory=MEMORY,user_id=data.get('user_id','local_user')); result['voice']=None; self.send_json(result)
   except Exception as e: self.send_json({'error':{'code':'CHAT_UNAVAILABLE','message':'Your AI service is unavailable.','technical':str(e)}},503)
  elif self.path=='/api/conversation': self.send_json({'id':MEMORY.create_conversation(data.get('user_id','local_user'),data.get('agent_id','agent_001'),data.get('title','New conversation'))})
  elif self.path=='/api/conversations': self.send_json(MEMORY.list_conversations(data.get('user_id','local_user'),data.get('agent_id','agent_001')))
  elif self.path=='/api/conversation/get': self.send_json(MEMORY.get_conversation(data['id'],data.get('user_id','local_user'),data.get('agent_id','agent_001')))
  elif self.path=='/api/conversation/delete': MEMORY.delete_conversation(data['id'],data.get('user_id','local_user'),data.get('agent_id','agent_001')); self.send_json({'ok':True})
  elif self.path=='/api/memory': MEMORY.remember(data.get('user_id','local_user'),data.get('agent_id','agent_001'),data.get('content','')); self.send_json({'ok':True})
  elif self.path in ('/api/synthesize_agent_speech','/api/preview_voice'):
   agent=data.get('agent',{'id':data.get('agent_id','agent_001'),'display_name':data.get('display_name','Billy'),'voice_id':data.get('voice_id','voice_001')}); p=profile_for(agent.get('voice_id','voice_001')); r=synthesize(agent,data.get('text','Hello, I am '+agent.get('display_name','Billy')),TestTTSProvider()); r['audio_base64']=base64.b64encode(r.pop('bytes')).decode(); r['profile_id']=profile_hash(p); r['status']='READY'; self.send_json(r)
  elif self.path=='/api/memories': self.send_json(MEMORY.list_memories(data.get('user_id','local_user'),data.get('agent_id','agent_001')))
  elif self.path=='/api/memory/delete': MEMORY.delete_memory(data['id'],data.get('user_id','local_user'),data.get('agent_id','agent_001')); self.send_json({'ok':True})
  else: self.send_json({'error':'not found'},404)
 def serve(self):
  p=Path(__file__).parent.parent/'ui'/self.path.lstrip('/')
  if not p.is_file(): self.send_error(404); return
  b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html' if p.suffix=='.html' else 'application/javascript'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,*a): pass
def main():
 port=int(os.getenv('OTACON_PORT','8787')); print(f'Wizard: http://127.0.0.1:{port}'); HTTPServer(('127.0.0.1',port),Handler).serve_forever()
if __name__=='__main__': main()
