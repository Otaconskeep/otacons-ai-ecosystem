from .platform import as_dict
def recommend_hardware_plan(hw):
 ranked=sorted(hw.gpus,key=lambda g:g.vram_gb,reverse=True); r={}
 if ranked:
  r={'primary_gpu':ranked[0].id,'generation_gpu':ranked[0].id,'fallback_gpu':ranked[1].id if len(ranked)>1 else 'cpu','utility_gpu':ranked[1].id if len(ranked)>1 else 'cpu'}
 else: r={x:'cpu' for x in ('primary_gpu','generation_gpu','fallback_gpu','utility_gpu')}
 det=getattr(hw,'gpu_detection',None) or {}
 # Do not present CPU-only roles as a successful "no GPU" scan when detection failed.
 scan_ok = det.get('status') in ('detected', 'none')
 return {
  'hardware':as_dict(hw),
  'gpu_roles':r,
  'scan_ok': scan_ok,
  'gpu_detection': det,
 }

