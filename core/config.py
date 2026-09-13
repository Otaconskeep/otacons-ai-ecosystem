import json,uuid
from pathlib import Path
def create_agent(name, index=1, role='primary', voice='default', personality='friendly', avatar=None):
 return {'id':f'agent_{index:03d}','display_name':name.strip() or 'Assistant','role':role,'voice':voice,'voice_id':'voice_001','personality':personality,'avatar':avatar}
def build_config(plan,name,features,branding=None,storage=None,agents=None,llm_service=None):
 root=(storage or {}).get('path') if isinstance(storage,dict) else None
 cfg={'system':{'install_id':str(uuid.uuid4()),'data_directory':str(Path(root)/'otacon-data') if root else None,'model_directory':str(Path(root)/'otacon-models') if root else None,'log_directory':str(Path(root)/'otacon-logs') if root else None},'branding':branding or {'product_name':'Otacon','tagline':'Local AI Command System','creator':'','show_creator_credit':False},'hardware':plan['hardware'],'gpu_roles':plan['gpu_roles'],'agents':agents or [create_agent(name)],'features':{f:True for f in features}}
 if llm_service:
  cfg['llm_service']=llm_service
 return cfg
def save(config,root):
 root.mkdir(parents=True,exist_ok=True); config['system'].update(data_directory=str(root/'runtime'),model_directory=str(root/'models'),log_directory=str(root/'logs')); p=root/'config.json'; p.write_text(json.dumps(config,indent=2)+'\n'); return p
def load(path): return json.loads(Path(path).read_text())
