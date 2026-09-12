from http.server import BaseHTTPRequestHandler,HTTPServer
import json,os
from pathlib import Path
from core.platform import detect
from core.planner import recommend_hardware_plan
from core.config import build_config,save
from core.storage import volumes,recommended_volume
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
   h=detect(); self.send_json({'config':build_config(recommend_hardware_plan(h),data.get('name','Assistant'),data.get('features',[])),'storage':data.get('storage') or recommended_volume()})
  elif self.path=='/api/save':
   root=Path(data.get('output') or (Path.home()/'.config/otacon')); self.send_json({'path':str(save(data['config'],root))})
  else: self.send_json({'error':'not found'},404)
 def serve(self):
  p=Path(__file__).parent.parent/'ui'/self.path.lstrip('/')
  if not p.is_file(): self.send_error(404); return
  b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html' if p.suffix=='.html' else 'application/javascript'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,*a): pass
def main():
 port=int(os.getenv('OTACON_PORT','8787')); print(f'Wizard: http://127.0.0.1:{port}'); HTTPServer(('127.0.0.1',port),Handler).serve_forever()
if __name__=='__main__': main()
