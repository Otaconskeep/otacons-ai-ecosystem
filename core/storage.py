from pathlib import Path
import shutil

def volumes(candidates=None):
    # Prefer portable candidates. Do not hard-prefer lab path /mnt/data.
    candidates=candidates or [Path.home(), Path('/var/tmp'), Path('/tmp'), Path('/')]
    # Include /mnt/data only when it actually exists on this host.
    mnt=Path('/mnt/data')
    if mnt.is_dir() and mnt not in candidates:
        candidates=[mnt]+list(candidates)
    out=[]; seen=set()
    for p in candidates:
        try:
            q=Path(p).resolve(); usage=shutil.disk_usage(q); key=str(usage)
            if key in seen: continue
            seen.add(key); out.append({'path':str(q),'free_gb':round(usage.free/1024**3,1),'total_gb':round(usage.total/1024**3,1),'recommended':False})
        except OSError: pass
    if out:
        # Recommend the volume with the most free space (tie-break: prefer $HOME).
        home=str(Path.home().resolve())
        best=max(out, key=lambda v: (v['free_gb'], 1 if v['path']==home else 0))
        best['recommended']=True
    return out

def recommended_volume():
    vs=volumes(); return next((v for v in vs if v['recommended']),vs[0] if vs else None)
