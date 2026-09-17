from __future__ import annotations
import os, platform, shutil, subprocess, threading
from dataclasses import dataclass, asdict, field
from pathlib import Path

@dataclass
class GPU:
 id:str; vendor:str; model:str; vram_gb:float; capability:str='GPU_SMALL'; node_id:str='node_001'
@dataclass
class Hardware:
 os:str; cpu_model:str; cpu_cores:int; ram_gb:float; free_storage_gb:float; gpus:list[GPU]; node_id:str='node_001'; hostname:str='local'; gpu_detection:dict=field(default_factory=dict)

# WSL2 exposes nvidia-smi + libs under /usr/lib/wsl/lib. systemd units do not
# inherit an interactive login PATH/LD_LIBRARY_PATH, so bare which()+exec fails
# even when the GPU is present. Keep absolute fallbacks + a WSL lib env.
_NVIDIA_SMI_CANDIDATES = (
  '/usr/lib/wsl/lib/nvidia-smi',
  '/usr/bin/nvidia-smi',
  '/usr/local/bin/nvidia-smi',
)
_WSL_LIB = '/usr/lib/wsl/lib'


def capability(v):
 return 'GPU_HIGH_END' if v>=20 else 'GPU_LARGE' if v>=12 else 'GPU_MEDIUM' if v>=8 else 'GPU_SMALL'


def _resolve_nvidia_smi() -> str | None:
  found = shutil.which('nvidia-smi')
  if found and os.path.isfile(found):
    return found
  for p in _NVIDIA_SMI_CANDIDATES:
    if os.path.isfile(p) and os.access(p, os.X_OK):
      return p
  return None


def _nvidia_smi_env() -> dict:
  """Minimal env so nvidia-smi works under systemd / stripped PATH (esp. WSL2)."""
  env = dict(os.environ)
  path_parts = env.get('PATH', '').split(':') if env.get('PATH') else []
  extras = ['/usr/local/sbin', '/usr/local/bin', '/usr/sbin', '/usr/bin', '/sbin', '/bin', _WSL_LIB]
  for p in extras:
    if p and p not in path_parts:
      path_parts.append(p)
  env['PATH'] = ':'.join(path_parts)
  ld_parts = env.get('LD_LIBRARY_PATH', '').split(':') if env.get('LD_LIBRARY_PATH') else []
  if os.path.isdir(_WSL_LIB) and _WSL_LIB not in ld_parts:
    ld_parts.insert(0, _WSL_LIB)
  if ld_parts:
    env['LD_LIBRARY_PATH'] = ':'.join(x for x in ld_parts if x)
  return env


def _nvidia_smi_query(smi: str, timeout_s: float = 5.0) -> str:
  """Run nvidia-smi without blocking the HTTP thread forever.

  On WSL2, nvidia-smi can enter uninterruptible sleep (D state). Python's
  subprocess timeout then never returns, which wedged the single-threaded
  Otacon server and made Open Codec / System Scan appear dead.
  """
  box: dict = {'out': None, 'exc': None}

  def _run():
    try:
      box['out'] = subprocess.check_output(
        [smi, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
        text=True, timeout=max(1, int(timeout_s)), env=_nvidia_smi_env(),
        stderr=subprocess.STDOUT,
      )
    except Exception as exc:  # noqa: BLE001 — surface to caller as-is
      box['exc'] = exc

  t = threading.Thread(target=_run, daemon=True, name='nvidia-smi-query')
  t.start()
  t.join(timeout_s + 1.0)
  if t.is_alive():
    raise TimeoutError(f'{smi} hung past {timeout_s}s (WSL GPU probe abandoned)')
  if box['exc'] is not None:
    raise box['exc']
  return box['out'] or ''


def _proc_nvidia_gpus() -> list[GPU]:
  """Fallback when nvidia-smi is skipped/hung: read /proc/driver/nvidia (common on WSL)."""
  root = Path('/proc/driver/nvidia/gpus')
  if not root.is_dir():
    return []
  found: list[GPU] = []
  try:
    entries = sorted(root.iterdir())
  except OSError:
    return []
  for i, entry in enumerate(entries):
    model = 'NVIDIA GPU'
    try:
      info = (entry / 'information').read_text(encoding='utf-8', errors='replace')
      for line in info.splitlines():
        if line.lower().startswith('model:'):
          model = line.split(':', 1)[1].strip() or model
          break
    except OSError:
      pass
    # VRAM unknown from proc — mark 0 so UI still shows the model name.
    found.append(GPU(f'gpu_{i+1:03d}', 'nvidia', model, 0.0, 'GPU_SMALL'))
  return found


def detect():
 try:
  import psutil
  ram=round(psutil.virtual_memory().total/1024**3,1); free=round(psutil.disk_usage(Path.home()).free/1024**3,1)
 except Exception:
  free=round(shutil.disk_usage(Path.home()).free/1024**3,1)
  ram=round(int(next(x for x in open('/proc/meminfo') if x.startswith('MemTotal')).split()[1])/1024**2,1)
 g=[]; gpu_status='unavailable'; gpu_message='NVIDIA inspection tool is unavailable in this environment.'
 smi=_resolve_nvidia_smi()
 skip = os.environ.get('OTACON_SKIP_NVIDIA_SMI', '').strip().lower() in ('1', 'true', 'yes')
 if skip:
  smi = None
  gpu_status = 'skipped'
  gpu_message = 'NVIDIA inspection skipped (OTACON_SKIP_NVIDIA_SMI).'
 if smi:
  gpu_status='none'; gpu_message='No NVIDIA GPUs were reported.'
  try:
   out=_nvidia_smi_query(smi, timeout_s=5.0)
   for i,line in enumerate(out.splitlines()):
    line=line.strip()
    if not line or ',' not in line:
     continue
    n,m=[x.strip() for x in line.split(',',1)]
    try:
     v=round(float(m)/1024,1)
    except ValueError:
     continue
    g.append(GPU(f'gpu_{i+1:03d}','nvidia',n,v,capability(v)))
   if g:
    gpu_status='detected'
    gpu_message=f'Detected {len(g)} NVIDIA GPU(s) via {smi}.'
   else:
    gpu_status='none'
    gpu_message=f'{smi} ran but reported no GPUs.'
  except (subprocess.CalledProcessError, subprocess.TimeoutExpired, TimeoutError, OSError) as exc:
   gpu_status='error'
   detail = ''
   if isinstance(exc, subprocess.CalledProcessError) and exc.output:
     detail = ' ' + str(exc.output).strip().splitlines()[-1][:160]
   elif isinstance(exc, TimeoutError):
     detail = ' ' + str(exc)
   gpu_message=f'GPU inspection failed ({type(exc).__name__}) using {smi}.{detail}'
 # Proc fallback: never claim "no GPU" when the driver is clearly present.
 if not g:
  proc_gpus = _proc_nvidia_gpus()
  if proc_gpus:
   g = proc_gpus
   gpu_status = 'detected'
   src = 'proc (nvidia-smi skipped)' if skip else 'proc fallback'
   gpu_message = f'Detected {len(g)} NVIDIA GPU(s) via {src}.'
 h=Hardware(platform.system(),platform.processor() or platform.machine(),os.cpu_count() or 1,ram,free,g)
 h.gpu_detection={'status':gpu_status,'message':gpu_message,'nvidia_smi':(_resolve_nvidia_smi() or '') if not skip else '', 'skipped': skip}
 return h


def as_dict(h):
 d=asdict(h); d['cpu']={'model':d.pop('cpu_model'),'cores':d.pop('cpu_cores')}
 d['node']={'id':d['node_id'],'hostname':d['hostname'],'cpu':d['cpu'],'ram_gb':d['ram_gb'],'gpus':d['gpus']}
 return d
