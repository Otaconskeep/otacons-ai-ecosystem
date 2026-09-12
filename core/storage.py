from pathlib import Path
import shutil

def volumes(candidates=None):
    candidates=candidates or [Path('/mnt/data'),Path.home(),Path('/')]
    out=[]; seen=set()
    for p in candidates:
        try:
            q=Path(p).resolve(); usage=shutil.disk_usage(q); key=str(usage)
            if key in seen: continue
            seen.add(key); out.append({'path':str(q),'free_gb':round(usage.free/1024**3,1),'total_gb':round(usage.total/1024**3,1),'recommended':str(q)== '/mnt/data'})
        except OSError: pass
    return out

def recommended_volume():
    vs=volumes(); return next((v for v in vs if v['recommended']),vs[0] if vs else None)
