"""Provider-neutral image generation and artifact handling."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
import hashlib, struct, zlib
from core.arbiter import WorkloadRequest

PROFILES={'draft':{'width':512,'height':512,'vram_gb':4},'standard':{'width':768,'height':768,'vram_gb':8},'quality':{'width':1024,'height':1024,'vram_gb':12}}

@dataclass
class ImageGenerationRequest:
    request_id: str; prompt: str; profile: str='standard'; negative_prompt: str|None=None
    width: int|None=None; height: int|None=None; seed: int|None=None; count: int=1
    service_id: str|None=None; agent_id: str|None=None; user_id: str='local_user'; conversation_id: str|None=None

@dataclass
class ImageGenerationResult:
    request_id: str; status: str; artifacts: list[dict]=field(default_factory=list)
    width: int=0; height: int=0; seed: int|None=None; provider: str=''; service_id: str=''; model_id: str=''
    error: dict|None=None; duration_seconds: float|None=None

class ImageProvider:
    provider_id='unknown'
    def health(self, model_id): raise NotImplementedError
    def resource_requirements(self, request): return {'vram_gb': PROFILES[request.profile]['vram_gb']}
    def generate(self, request, service_id, model_id): raise NotImplementedError
    def cancel(self, request_id): return False

def _png(width,height,seed):
    # Small deterministic RGB PNG; no private or user data is embedded.
    row=b''.join(bytes(((x+seed)%256,(y+seed*3)%256,(x+y+seed)%256)) for y in range(height) for x in range(width))
    raw=b''.join(b'\x00'+row[y*width*3:(y+1)*width*3] for y in range(height))
    def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')

class TestImageProvider(ImageProvider):
    provider_id='test'
    def health(self, model_id): return 'ONLINE','deterministic test provider'
    def generate(self, request, service_id, model_id):
        p=PROFILES[request.profile]; w=request.width or p['width']; h=request.height or p['height']; seed=request.seed if request.seed is not None else 7
        return ImageGenerationResult(request.request_id,'COMPLETED',width=w,height=h,seed=seed,provider=self.provider_id,service_id=service_id,model_id=model_id,artifacts=[{'bytes':_png(w,h,seed),'mime_type':'image/png'}])

class StableDiffusionProvider(ImageProvider):
    provider_id='stable_diffusion'
    def __init__(self, endpoint=''): self.endpoint=endpoint
    def health(self, model_id): return ('OFFLINE','image runtime endpoint is not configured') if not self.endpoint else ('UNKNOWN','external provider validation pending')
    def generate(self, request, service_id, model_id): raise RuntimeError('IMAGE_PROVIDER_UNAVAILABLE: configure a public image service')

def validate_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)<40: raise ValueError('IMAGE_ARTIFACT_INVALID')
    w,h=struct.unpack('>II',data[16:24])
    if not w or not h: raise ValueError('IMAGE_ARTIFACT_INVALID')
    return w,h

class ImageProductionManager:
    def __init__(self, arbiter, provider, service_id='service_image_test', model_id='image_standard', root=None):
        self.arbiter=arbiter; self.provider=provider; self.service_id=service_id; self.model_id=model_id
        self.root=Path(root or (Path.home()/'.config'/'otacon'/'runtime'/'generated')); self.root.mkdir(parents=True,exist_ok=True)
    def generate(self, request):
        if request.profile not in PROFILES or not request.prompt.strip(): return ImageGenerationResult(request.request_id,'FAILED',error={'code':'IMAGE_REQUEST_INVALID'})
        req=WorkloadRequest('image_'+request.request_id,'IMAGE_GENERATION','image_generation',self.provider.resource_requirements(request),service_id=self.service_id,agent_id=request.agent_id)
        allocation=self.arbiter.request(req)
        if allocation.get('status')!='RESOURCE_AVAILABLE': return ImageGenerationResult(request.request_id,'WAITING_RESOURCE',error={'code':'IMAGE_'+allocation.get('status','RESOURCE_BUSY')})
        lease=allocation['lease']
        try:
            result=self.provider.generate(request,self.service_id,self.model_id)
            for artifact in result.artifacts:
                w,h=validate_png(artifact['bytes']); aid='artifact_'+hashlib.sha1((request.request_id+str(w)+str(h)).encode()).hexdigest()[:12]
                path=self.root/(aid+'.png'); path.write_bytes(artifact['bytes']); artifact.update({'artifact_id':aid,'path':str(path),'width':w,'height':h,'request_id':request.request_id,'created_at':datetime.now(timezone.utc).isoformat(),'user_id':request.user_id,'agent_id':request.agent_id,'conversation_id':request.conversation_id})
            result.artifacts=[{k:v for k,v in a.items() if k!='bytes'} for a in result.artifacts]; return result
        except Exception as exc: return ImageGenerationResult(request.request_id,'FAILED',provider=self.provider.provider_id,error={'code':'IMAGE_GENERATION_FAILED','message':str(exc)})
        finally: self.arbiter.release(lease.lease_id,req.owner_id)
