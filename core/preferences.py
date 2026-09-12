import json
from pathlib import Path
class Preferences:
 def __init__(self,path):
  self.path=Path(path)
  try: self.data=json.loads(self.path.read_text()) if self.path.is_file() and self.path.stat().st_size else {}
  except json.JSONDecodeError: self.data={}
 def get_auto_speak(self,user,agent): return bool(self.data.get(user,{}).get(agent,False))
 def set_auto_speak(self,user,agent,value): self.data.setdefault(user,{})[agent]=bool(value); self.path.parent.mkdir(parents=True,exist_ok=True); self.path.write_text(json.dumps(self.data,indent=2)+'\n')
