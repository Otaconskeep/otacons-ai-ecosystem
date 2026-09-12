"""Authenticated, bounded artifact transfer with atomic promotion."""
from pathlib import Path
import hashlib, os
ALLOWED={'image/png','video/x-msvideo','audio/wav'}
def receive_artifact(data, destination, *, workload_id, expected_workload_id, mime, checksum, max_bytes=50*1024*1024):
 if workload_id!=expected_workload_id: raise ValueError('ARTIFACT_WORKLOAD_MISMATCH')
 if mime not in ALLOWED: raise ValueError('ARTIFACT_MIME_UNSUPPORTED')
 if len(data)>max_bytes: raise ValueError('ARTIFACT_TOO_LARGE')
 if hashlib.sha256(data).hexdigest()!=checksum: raise ValueError('ARTIFACT_CHECKSUM_FAILED')
 dest=Path(destination).resolve(); dest.parent.mkdir(parents=True,exist_ok=True); tmp=dest.with_name('.'+dest.name+'.partial'); tmp.write_bytes(data); os.replace(tmp,dest); return dest
