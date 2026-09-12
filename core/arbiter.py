"""Small provider-neutral compute arbiter for local and distributed resources."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib

AVAILABLE='AVAILABLE'; BUSY='BUSY'; RESERVED='RESERVED'; DEGRADED='DEGRADED'; OFFLINE='OFFLINE'; UNKNOWN='UNKNOWN'
PRIORITY={'INTERACTIVE_CHAT':100,'SPEECH_TO_TEXT':90,'TEXT_TO_SPEECH':85,'IMAGE_GENERATION':60,'VIDEO_RENDER':50,'MODEL_TRAINING':20,'MODEL_LOADING':30,'MAINTENANCE':10}

@dataclass
class ComputeResource:
    id: str
    kind: str = 'GPU'
    owner_resource_id: str = ''
    exposed_to: list[str] = field(default_factory=list)
    capacity: dict = field(default_factory=dict)
    used: dict = field(default_factory=dict)
    state: str = AVAILABLE
    metadata: dict = field(default_factory=dict)
    def free(self, key='vram_gb'):
        return float(self.capacity.get(key, 0)) - float(self.used.get(key, 0))

@dataclass
class WorkloadRequest:
    workload_id: str
    workload_class: str
    capability: str
    requirements: dict = field(default_factory=dict)
    priority: int | None = None
    service_id: str | None = None
    agent_id: str | None = None
    preemptible: bool = True
    expected_duration: float | None = None
    owner_id: str = 'control-plane'
    timeout_seconds: int = 300
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    def rank(self): return self.priority if self.priority is not None else PRIORITY.get(self.workload_class, 50)

@dataclass
class Lease:
    lease_id: str
    workload_id: str
    resource_id: str
    service_id: str | None
    owner_id: str
    state: str = 'GRANTED'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    heartbeat_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_seconds: int = 300
    revision: int = 1

@dataclass
class Residency:
    resource_id: str
    service_id: str
    model_id: str
    vram_gb: float
    state: str = 'IDLE_RECLAIMABLE'
    reclaimer: object | None = None

class ResourceTelemetryProvider:
    def snapshot(self): raise NotImplementedError

class StaticTelemetryProvider(ResourceTelemetryProvider):
    def __init__(self, resources): self.resources = resources
    def snapshot(self): return list(self.resources)

class ResourceArbiter:
    def __init__(self, resources, *, telemetry=None, now=None):
        self.resources={r.id:r for r in resources}; self.telemetry=telemetry
        self.leases={}; self.queue=[]; self.residency=[]; self.revision=0; self._now=now
        self.failures={}; self.circuits={}; self.events=[]
    def snapshot(self):
        if self.telemetry:
            for r in self.telemetry.snapshot(): self.resources[r.id]=r
        return list(self.resources.values())
    def _eligible(self, request, r):
        if r.state not in (AVAILABLE, BUSY): return False
        req=request.requirements; cap=req.get('vram_gb',0)
        if cap and r.free('vram_gb') < cap: return False
        if req.get('capability') and req['capability'] not in r.metadata.get('capabilities',[]): return False
        allowed=req.get('resource_ids');
        if allowed and r.id not in allowed: return False
        exposed=req.get('runtime_id')
        if exposed and exposed not in r.exposed_to: return False
        return True
    def request(self, request):
        if self.circuits.get(request.service_id)=='CIRCUIT_OPEN': return {'status':'CIRCUIT_OPEN'}
        candidates=[r for r in self.snapshot() if self._eligible(request,r)]
        if not candidates:
            needed = float(request.requirements.get('vram_gb', 0))
            if needed:
                self.reclaim_idle(needed)
                candidates=[r for r in self.snapshot() if self._eligible(request,r)]
        if not candidates:
            self.queue.append(request); self.events.append({'event':'queue','workload_id':request.workload_id})
            if any(r.state == OFFLINE for r in self.resources.values()): return {'status':'RESOURCE_OFFLINE'}
            if any(request.requirements.get('vram_gb',0)>r.capacity.get('vram_gb',0) for r in self.resources.values()): return {'status':'INSUFFICIENT_VRAM'}
            return {'status':'RESOURCE_BUSY'}
        r=max(candidates,key=lambda x:x.free('vram_gb'))
        lid='lease_'+hashlib.sha1((request.workload_id+r.id).encode()).hexdigest()[:12]
        if lid in self.leases and self.leases[lid].state in ('ACTIVE','GRANTED'): return {'status':'LEASE_CONFLICT'}
        lease=Lease(lid,request.workload_id,r.id,request.service_id,request.owner_id); self.leases[lid]=lease
        r.used['vram_gb']=float(r.used.get('vram_gb',0))+float(request.requirements.get('vram_gb',0)); r.state=BUSY
        self.revision+=1; self.events.append({'event':'lease_granted','lease_id':lid,'resource_id':r.id}); return {'status':'RESOURCE_AVAILABLE','lease':lease}
    def activate(self, lease_id, owner_id):
        l=self.leases[lease_id]
        if l.owner_id!=owner_id: return {'status':'LEASE_CONFLICT'}
        l.state='ACTIVE'; l.revision+=1; return {'status':'ACTIVE','lease':l}
    def heartbeat(self, lease_id, owner_id):
        l=self.leases.get(lease_id)
        if not l or l.owner_id!=owner_id: return {'status':'LEASE_CONFLICT'}
        l.heartbeat_at=datetime.now(timezone.utc).isoformat(); l.revision+=1; return {'status':'OK'}
    def release(self, lease_id, owner_id):
        l=self.leases.get(lease_id)
        if not l or l.owner_id!=owner_id: return {'status':'LEASE_CONFLICT'}
        l.state='RELEASED'; self.resources[l.resource_id].state=AVAILABLE; self.events.append({'event':'lease_released','lease_id':lease_id}); return {'status':'RELEASED'}
    def recover_stale(self, grace_seconds=30):
        now=datetime.now(timezone.utc); recovered=[]
        for l in self.leases.values():
            if l.state not in ('ACTIVE','GRANTED'): continue
            try: age=(now-datetime.fromisoformat(l.heartbeat_at)).total_seconds()
            except ValueError: age=0
            if age>l.ttl_seconds+grace_seconds:
                l.state='EXPIRED'; self.resources[l.resource_id].state=AVAILABLE; recovered.append(l.lease_id)
        return recovered
    def reclaim_idle(self, required_vram):
        freed=0
        for x in self.residency:
            if x.state!='IDLE_RECLAIMABLE': continue
            if x.reclaimer and not x.reclaimer(): continue
            x.state='UNLOADED'; self.resources[x.resource_id].used['vram_gb']=max(0,self.resources[x.resource_id].used.get('vram_gb',0)-x.vram_gb); freed+=x.vram_gb
            if freed>=required_vram: break
        return freed
    def record_failure(self, service_id, signature, max_retries=3):
        key=(service_id,signature); count=self.failures.get(key,0)+1; self.failures[key]=count
        if count>=max_retries: self.circuits[service_id]='CIRCUIT_OPEN'
        return {'retry_count':count,'state':self.circuits.get(service_id,'CLOSED'),'next_retry_seconds':min(300,2**count)}

def default_resources():
    return [ComputeResource('resource_cpu_001','CPU',capacity={'ram_gb':32},metadata={'capabilities':['cpu']}), ComputeResource('resource_gpu_001','GPU','host_local',capacity={'vram_gb':24},metadata={'capabilities':['conversational_llm','image_generation']})]
