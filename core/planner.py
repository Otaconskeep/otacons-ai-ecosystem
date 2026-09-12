from .platform import as_dict
def recommend_hardware_plan(hw):
 ranked=sorted(hw.gpus,key=lambda g:g.vram_gb,reverse=True); r={}
 if ranked:
  r={'primary_gpu':ranked[0].id,'generation_gpu':ranked[0].id,'fallback_gpu':ranked[1].id if len(ranked)>1 else 'cpu','utility_gpu':ranked[1].id if len(ranked)>1 else 'cpu'}
 else: r={x:'cpu' for x in ('primary_gpu','generation_gpu','fallback_gpu','utility_gpu')}
 return {'hardware':as_dict(hw),'gpu_roles':r}
