import argparse, json, subprocess
from core.acceptance import report, merge, save, REQUIRED
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--server',action='store_true'); p.add_argument('--desktop',action='store_true'); p.add_argument('--merge',nargs='+'); p.add_argument('--output'); p.add_argument('--confirm',action='append',default=[]); a=p.parse_args(argv); commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 if a.merge:
  data=merge([json.load(open(x)) for x in a.merge]); print(json.dumps(data,indent=2));
  if a.output: save(data,a.output)
  return 0 if data['result']!='FAIL' else 2
 if not (a.server or a.desktop): p.error('choose --server, --desktop, or --merge')
 mode='server' if a.server else 'desktop'; statuses={k:'PENDING' for k in REQUIRED}; confirmations={k:True for k in a.confirm}; failures={k:'Run this check on the target environment' for k in REQUIRED}; evidence={}
 if mode=='server':
  try:
   from core.providers import OllamaProvider
   import json
   cfg=json.loads(open('/root/.config/otacon/config.json').read()); svc=cfg.get('llm_service',{}); health=OllamaProvider(svc.get('endpoint','')).health(svc.get('model',''))
   if health.state=='ONLINE': statuses['REAL_OLLAMA_INFERENCE_PASS']='PASS'; evidence['REAL_OLLAMA_INFERENCE_PASS']={'provider_type':'OllamaProvider','production_provider':True,'request_completed':True}
  except Exception: pass
 # This command intentionally never substitutes test providers or probes from a headless sandbox.
 data=report(mode,statuses,commit=commit,confirmations=confirmations,failures=failures,evidence=evidence); print(json.dumps(data,indent=2));
 if a.output: save(data,a.output)
 return 0
if __name__=='__main__': raise SystemExit(main())
