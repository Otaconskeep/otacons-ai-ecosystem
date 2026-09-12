"""Secure logical node registry and structured remote workload protocol."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import secrets, hashlib

PROTOCOL_VERSION=1
@dataclass
class Node:
 node_id:str; display_name:str; node_type:str='WORKER'; trust_state:str='UNPAIRED'; status:str='OFFLINE'; protocol_version:int=PROTOCOL_VERSION; last_seen:str|None=None; resources:list[dict]=field(default_factory=list); services:list[dict]=field(default_factory=list); metadata:dict=field(default_factory=dict)
@dataclass
class PairingCode:
 code_hash:str; expires_at:datetime; used:bool=False
@dataclass
class RemoteWorkload:
 workload_id:str; node_id:str; capability:str; payload:dict; state:str='DISPATCHING'; revision:int=1; owner_id:str='control-plane'; result:dict|None=None
class NodeRegistry:
 def __init__(self): self.nodes={}; self.codes={}; self.workloads={}
 def create_pairing(self,ttl_seconds=300):
  code=secrets.token_urlsafe(8); self.codes[hashlib.sha256(code.encode()).hexdigest()]=PairingCode(hashlib.sha256(code.encode()).hexdigest(),datetime.now(timezone.utc)+timedelta(seconds=ttl_seconds)); return code
 def approve_pairing(self,code,display_name,node_type='WORKER'):
  h=hashlib.sha256(code.encode()).hexdigest(); c=self.codes.get(h)
  if not c or c.used or datetime.now(timezone.utc)>=c.expires_at: return None,'PAIRING_EXPIRED'
  c.used=True; node=Node('node_'+secrets.token_hex(8),display_name,node_type,'TRUSTED','ONLINE'); self.nodes[node.node_id]=node; return node,None
 def revoke(self,node_id):
  n=self.nodes.get(node_id)
  if not n:return False
  n.trust_state='REVOKED'; n.status='OFFLINE'; return True
 def heartbeat(self,node_id,resources=None,services=None):
  n=self.nodes.get(node_id)
  if not n or n.trust_state!='TRUSTED': return {'status':'NODE_AUTH_FAILED'}
  n.status='ONLINE'; n.last_seen=datetime.now(timezone.utc).isoformat();
  if resources is not None:n.resources=resources
  if services is not None:n.services=services
  return {'status':'OK','node_id':node_id}
 def mark_offline(self,offline_after=90):
  now=datetime.now(timezone.utc); changed=[]
  for n in self.nodes.values():
   if n.trust_state!='TRUSTED' or not n.last_seen: continue
   if (now-datetime.fromisoformat(n.last_seen)).total_seconds()>offline_after: n.status='OFFLINE'; changed.append(n.node_id)
  return changed
 def dispatch(self,node_id,workload_id,capability,payload,owner_id='control-plane'):
  n=self.nodes.get(node_id)
  if not n or n.trust_state!='TRUSTED': return None,'NODE_UNTRUSTED'
  if n.status!='ONLINE': return None,'NODE_OFFLINE'
  if workload_id in self.workloads:
   w=self.workloads[workload_id]
   return w,('DUPLICATE' if w.owner_id==owner_id else 'LEASE_CONFLICT')
  if not any(capability in s.get('capabilities',[]) and s.get('health','READY')=='READY' for s in n.services): return None,'NODE_SERVICE_UNAVAILABLE'
  w=RemoteWorkload(workload_id,node_id,capability,dict(payload),owner_id=owner_id); self.workloads[workload_id]=w; return w,None
 def complete(self,workload_id,result,revision=1):
  w=self.workloads.get(workload_id)
  if not w or revision!=w.revision:return False
  w.result=result; w.state='COMPLETED'; w.revision+=1; return True
class TestNodeAgent:
 def __init__(self,registry,node_id,services=None,resources=None): self.registry=registry; self.node_id=node_id; self.services=services or []; self.resources=resources or []
 def connect(self): return self.registry.heartbeat(self.node_id,self.resources,self.services)
 def execute(self,workload):
  if workload.workload_id not in self.registry.workloads:return {'status':'REMOTE_JOB_LOST'}
  result={'workload_id':workload.workload_id,'status':'COMPLETED','artifact':'controlled-result'}; self.registry.complete(workload.workload_id,result,workload.revision); return result
