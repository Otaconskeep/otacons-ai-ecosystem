"""Persistent structured worker process boundary; never executes arbitrary shell."""
from pathlib import Path
import json
class WorkerState:
 def __init__(self,path): self.path=Path(path); self.workloads={}; self.load()
 def load(self):
  if self.path.is_file(): self.workloads=json.loads(self.path.read_text()).get('workloads',{})
 def save(self): self.path.parent.mkdir(parents=True,exist_ok=True); self.path.write_text(json.dumps({'workloads':self.workloads}))
 def accept(self,workload_id,payload):
  if workload_id in self.workloads:return self.workloads[workload_id]
  self.workloads[workload_id]={'state':'RUNNING','payload':payload,'revision':1}; self.save(); return self.workloads[workload_id]
 def cancel(self,workload_id,revision,owner):
  w=self.workloads.get(workload_id)
  if not w or revision!=w['revision'] or owner!='control-plane': return 'CANCEL_REJECTED'
  w['state']='CANCELED'; w['revision']+=1; self.save(); return 'CANCELED'
 def reconcile(self,workload_id): return self.workloads.get(workload_id,{'state':'LOST'})
