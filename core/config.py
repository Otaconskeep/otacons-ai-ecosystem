import json,uuid
def build_config(plan,name,features,branding=None):
 return {'system':{'install_id':str(uuid.uuid4()),'data_directory':None,'model_directory':None,'log_directory':None},'branding':branding or {'product_name':'Otacon','tagline':'Local AI Command System','creator':'','show_creator_credit':False},'hardware':plan['hardware'],'gpu_roles':plan['gpu_roles'],'agents':[{'id':'agent_001','display_name':name,'role':'primary','voice':'default','personality':'friendly','avatar':None}],'features':{f:True for f in features}}
def save(config,root):
 root.mkdir(parents=True,exist_ok=True); config['system'].update(data_directory=str(root/'runtime'),model_directory=str(root/'models'),log_directory=str(root/'logs')); p=root/'config.json'; p.write_text(json.dumps(config,indent=2)+'\n'); return p
