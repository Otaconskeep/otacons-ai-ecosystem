"""Provider-neutral video production contracts and manager."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
import hashlib, struct
from core.arbiter import WorkloadRequest

VIDEO_PROFILES={
 'draft':{'width':640,'height':352,'execution_class':'FAST','inference_steps_reference':4,'vram_gb':8},
 'normal':{'width':864,'height':480,'execution_class':'BALANCED','inference_steps_reference':20,'vram_gb':12},
 'final':{'width':1344,'height':768,'execution_class':'QUALITY','inference_steps_reference':35,'vram_gb':20},
}
@dataclass
class VideoGenerationRequest:
 request_id:str; prompt:str; mode:str='TEXT_TO_VIDEO'; profile:str='normal'; source_artifact_id:str|None=None; width:int|None=None; height:int|None=None; duration:float=2.0; fps:int=8; seed:int|None=None; audio_requested:bool=False; user_id:str='local_user'; agent_id:str|None=None; conversation_id:str|None=None
@dataclass
class VideoGenerationResult:
 request_id:str; status:str; artifacts:list[dict]=field(default_factory=list); width:int=0; height:int=0; duration:float=0; fps:int=0; seed:int|None=None; provider:str=''; service_id:str=''; model_id:str=''; execution_profile:dict=field(default_factory=dict); error:dict|None=None
class VideoProvider:
 provider_id='unknown'
 def health(self,model_id): raise NotImplementedError
 def capabilities(self): return {'supports_text_to_video':False,'supports_image_to_video':False,'supports_cancellation':False,'supports_accelerated_path':False}
 def execution_plan(self,request): raise NotImplementedError
 def generate(self,request,service_id,model_id,plan): raise NotImplementedError
 def cancel(self,request_id): return False
def _avi(seed):
 payload=b'OTACON-TEST-VIDEO-'+bytes([seed%256])*32
 return b'RIFF'+struct.pack('<I',len(payload)+4)+b'AVI '+payload
class TestVideoProvider(VideoProvider):
 provider_id='test'
 def health(self,model_id): return 'ONLINE','deterministic test provider'
 def capabilities(self): return {'supports_text_to_video':True,'supports_image_to_video':True,'supports_cancellation':True,'supports_accelerated_path':True,'supports_progress':False}
 def execution_plan(self,request):
  p=VIDEO_PROFILES[request.profile]; return {'execution_class':p['execution_class'],'width':request.width or p['width'],'height':request.height or p['height'],'inference_steps':p['inference_steps_reference'],'acceleration_mode':'provider_resolved','fallback_used':False}
 def generate(self,request,service_id,model_id,plan):
  seed=request.seed if request.seed is not None else 11
  return VideoGenerationResult(request.request_id,'COMPLETED',width=plan['width'],height=plan['height'],duration=request.duration,fps=request.fps,seed=seed,provider=self.provider_id,service_id=service_id,model_id=model_id,execution_profile=plan,artifacts=[{'bytes':_avi(seed),'mime_type':'video/x-msvideo'}])
class ComfyUIProvider(VideoProvider):
 provider_id='comfyui'
 def __init__(self,endpoint=''): self.endpoint=endpoint
 def health(self,model_id): return ('OFFLINE','video runtime endpoint is not configured') if not self.endpoint else ('UNKNOWN','external provider validation pending')
 def execution_plan(self,request):
  p=VIDEO_PROFILES[request.profile]; return {'execution_class':p['execution_class'],'width':request.width or p['width'],'height':request.height or p['height'],'inference_steps':p['inference_steps_reference'],'acceleration_mode':'provider_resolved','fallback_used':False}
 def generate(self,*args,**kwargs): raise RuntimeError('VIDEO_PROVIDER_UNAVAILABLE: configure a public video service')
def validate_video(data):
 if not data.startswith(b'RIFF') or b'AVI ' not in data[:16] or len(data)<16: raise ValueError('VIDEO_ARTIFACT_INVALID')
class VideoProductionManager:
 def __init__(self,arbiter,provider,service_id='service_video_test',model_id='video_standard',root=None): self.arbiter=arbiter; self.provider=provider; self.service_id=service_id; self.model_id=model_id; self.root=Path(root or Path.home()/'.config'/'otacon'/'runtime'/'generated'); self.root.mkdir(parents=True,exist_ok=True)
 def generate(self,request):
  if request.profile not in VIDEO_PROFILES or request.mode not in ('TEXT_TO_VIDEO','IMAGE_TO_VIDEO') or not request.prompt.strip(): return VideoGenerationResult(request.request_id,'FAILED',error={'code':'VIDEO_REQUEST_INVALID'})
  if request.mode=='IMAGE_TO_VIDEO' and not request.source_artifact_id: return VideoGenerationResult(request.request_id,'FAILED',error={'code':'VIDEO_SOURCE_INVALID'})
  plan=self.provider.execution_plan(request); req=WorkloadRequest('video_'+request.request_id,'VIDEO_RENDER','video_generation',{'vram_gb':VIDEO_PROFILES[request.profile]['vram_gb']},service_id=self.service_id,agent_id=request.agent_id,preemptible=False)
  allocation=self.arbiter.request(req)
  if allocation.get('status')!='RESOURCE_AVAILABLE': return VideoGenerationResult(request.request_id,'WAITING_RESOURCE',error={'code':'VIDEO_'+allocation.get('status','RESOURCE_BUSY')})
  lease=allocation['lease']
  try:
   result=self.provider.generate(request,self.service_id,self.model_id,plan)
   for a in result.artifacts:
    validate_video(a['bytes']); aid='artifact_'+hashlib.sha1((request.request_id+str(lease.lease_id)).encode()).hexdigest()[:12]; path=self.root/(aid+'.avi'); path.write_bytes(a['bytes']); a.update({'artifact_id':aid,'path':str(path),'request_id':request.request_id,'workload_id':req.workload_id,'lease_id':lease.lease_id,'user_id':request.user_id,'agent_id':request.agent_id,'conversation_id':request.conversation_id,'created_at':datetime.now(timezone.utc).isoformat()})
   result.artifacts=[{k:v for k,v in a.items() if k!='bytes'} for a in result.artifacts]; return result
  except Exception as exc: return VideoGenerationResult(request.request_id,'FAILED',error={'code':'VIDEO_GENERATION_FAILED','message':str(exc)})
  finally: self.arbiter.release(lease.lease_id,req.owner_id)
