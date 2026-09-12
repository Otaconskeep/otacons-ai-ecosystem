from __future__ import annotations
import os, platform, shutil, subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
@dataclass
class GPU:
 id:str; vendor:str; model:str; vram_gb:float; capability:str='GPU_SMALL'; node_id:str='node_001'
@dataclass
class Hardware:
 os:str; cpu_model:str; cpu_cores:int; ram_gb:float; free_storage_gb:float; gpus:list[GPU]; node_id:str='node_001'; hostname:str='local'
def capability(v):
 return 'GPU_HIGH_END' if v>=20 else 'GPU_LARGE' if v>=12 else 'GPU_MEDIUM' if v>=8 else 'GPU_SMALL'
def detect():
 try:
  import psutil
  ram=round(psutil.virtual_memory().total/1024**3,1); free=round(psutil.disk_usage(Path.home()).free/1024**3,1)
 except Exception:
  free=round(shutil.disk_usage(Path.home()).free/1024**3,1)
  ram=round(int(next(x for x in open('/proc/meminfo') if x.startswith('MemTotal')).split()[1])/1024**2,1)
 g=[]
 if shutil.which('nvidia-smi'):
  try:
   out=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader,nounits'],text=True,timeout=5)
   for i,line in enumerate(out.splitlines()):
    n,m=[x.strip() for x in line.split(',',1)]; v=round(float(m)/1024,1); g.append(GPU(f'gpu_{i+1:03d}','nvidia',n,v,capability(v)))
  except Exception: pass
 return Hardware(platform.system(),platform.processor() or platform.machine(),os.cpu_count() or 1,ram,free,g)
def as_dict(h):
 d=asdict(h); d['cpu']={'model':d.pop('cpu_model'),'cores':d.pop('cpu_cores')}
 d['node']={'id':d['node_id'],'hostname':d['hostname'],'cpu':d['cpu'],'ram_gb':d['ram_gb'],'gpus':d['gpus']}
 return d
