from dataclasses import dataclass, field
@dataclass
class Action:
 id:str; label:str; state:str='PENDING'; result:dict=field(default_factory=dict); error:dict|None=None; technical:list[str]=field(default_factory=list); retries:int=0
 def run(self, fn):
  self.state='RUNNING'
  try: self.result=fn() or {}; self.state='SUCCEEDED'; return self
  except Exception as e: self.state='FAILED'; self.error={'message':str(e),'type':type(e).__name__}; self.technical.append(repr(e)); return self
CHAT_ACTIONS=[('CHECK_LLM_RUNTIME','Checking AI engine'),('INSTALL_LLM_RUNTIME','Installing AI engine'),('CHECK_MODEL','Checking model'),('CHECK_STORAGE','Checking model storage'),('DOWNLOAD_MODEL','Downloading model'),('START_LLM_SERVICE','Starting AI service'),('REGISTER_LLM_SERVICE','Registering AI service'),('VALIDATE_LLM_SERVICE','Validating AI service'),('CREATE_AGENT','Creating agent'),('VALIDATE_AGENT_CHAT','Testing agent chat')]
def action_plan(): return [Action(i,l) for i,l in CHAT_ACTIONS]
