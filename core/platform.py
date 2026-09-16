from __future__ import annotations
import os, platform, shutil, subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
@dataclass
class GPU:
 id:str; vendor:str; model:str; vram_gb:float; capability:str='GPU_SMALL'; node_id:str='node_001'
@dataclass
class Hardware:
 os:str; cpu_model:str; cpu_cores:int; ram_gb:float; free_storage_gb:float; gpus:list[GPU]; node_id:str='node_001'; hostname:str='local'; gpu_detection:dict=field(default_factory=dict)
def capability(v):
 return 'GPU_HIGH_END' if v>=20 else 'GPU_LARGE' if v>=12 else 'GPU_MEDIUM' if v>=8 else 'GPU_SMALL'
def detect():
 try:
  import psutil
  ram=round(psutil.virtual_memory().total/1024**3,1); free=round(psutil.disk_usage(Path.home()).free/1024**3,1)
 except Exception:
  free=round(shutil.disk_usage(Path.home()).free/1024**3,1)
  ram=round(int(next(x for x in open('/proc/meminfo') if x.startswith('MemTotal')).split()[1])/1024**2,1)
 g=[]; gpu_status='unavailable'; gpu_message='NVIDIA inspection tool is unavailable in this environment.'
 # shutil.which() only searches $PATH, which a systemd-managed service does
 # NOT inherit from the interactive login shell that originally ran the
 # installer. On WSL2 specifically, nvidia-smi lives under /usr/lib/wsl/lib,
 # a directory only an interactive shell's PATH includes -- so the same
 # machine reports a real GPU when install_otacon.sh's bash-level check
 # runs, then reports "unavailable" the moment this Python scan runs inside
 # the systemd service. Check a short list of known-good absolute paths as
 # a fallback before giving up.
 smi=shutil.which('nvidia-smi') or next((p for p in (
  '/usr/lib/wsl/lib/nvidia-smi', '/usr/bin/nvidia-smi', '/usr/local/bin/nvidia-smi',
 ) if os.path.isfile(p)), None)
 if smi:
  gpu_status='none'; gpu_message='No NVIDIA GPUs were reported.'
  try:
   out=subprocess.check_output([smi,'--query-gpu=name,memory.total','--format=csv,noheader,nounits'],text=True,timeout=5)
   for i,line in enumerate(out.splitlines()):
    n,m=[x.strip() for x in line.split(',',1)]; v=round(float(m)/1024,1); g.append(GPU(f'gpu_{i+1:03d}','nvidia',n,v,capability(v)))
   gpu_status='detected' if g else 'none'
  except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
   gpu_status='error'; gpu_message=f'GPU inspection failed: {type(exc).__name__}.'
 h=Hardware(platform.system(),platform.processor() or platform.machine(),os.cpu_count() or 1,ram,free,g)
 h.gpu_detection={'status':gpu_status,'message':gpu_message}
 return h
def as_dict(h):
 d=asdict(h); d['cpu']={'model':d.pop('cpu_model'),'cores':d.pop('cpu_cores')}
 d['node']={'id':d['node_id'],'hostname':d['hostname'],'cpu':d['cpu'],'ram_gb':d['ram_gb'],'gpus':d['gpus']}
 return d
