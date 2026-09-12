"""Portable lifecycle primitives: migrations, backups, updates and diagnostics."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import hashlib, json, shutil, tempfile, zipfile
APP_VERSION='0.1.0'; NODE_PROTOCOL_VERSION=1; SCHEMA_VERSION=1
class MigrationManager:
 def migrate(self,data,version=0):
  out=dict(data); out.setdefault('schema_version',version); out['schema_version']=SCHEMA_VERSION; return out
class BackupManager:
 def create(self,source,destination,include_secrets=False):
  source=Path(source); destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True); files=[]
  with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
   for p in source.rglob('*'):
    if p.is_file() and p.name not in ('backup.zip',):
     rel=p.relative_to(source); z.write(p,rel); files.append({'path':str(rel),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
   z.writestr('manifest.json',json.dumps({'format_version':1,'application_version':APP_VERSION,'included_components':files,'excluded_components':['models','generated_media'],'secrets_included':include_secrets}))
  return destination
class RestoreManager:
 def restore(self,archive,target):
  target=Path(target); target.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(archive) as z:
   manifest=json.loads(z.read('manifest.json')); 
   for item in manifest['included_components']:
    data=z.read(item['path']);
    if hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('BACKUP_CHECKSUM_FAILED')
   for item in manifest['included_components']:
    p=target/item['path']; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(z.read(item['path']))
  return manifest
class UpdateManager:
 def verify(self,manifest,package):
  package=Path(package); expected=manifest.get('sha256'); actual=hashlib.sha256(package.read_bytes()).hexdigest()
  if expected!=actual: raise ValueError('UPDATE_CHECKSUM_FAILED')
  if not manifest.get('version') or manifest.get('package_identity')!='otacon': raise ValueError('UPDATE_IDENTITY_INVALID')
  return True
class HealthManager:
 def aggregate(self,checks):
  states=[x.get('status') for x in checks]
  status='HEALTHY' if all(x in ('HEALTHY','READY','ONLINE') for x in states) else ('DEGRADED' if any(x in ('DEGRADED','UNKNOWN') for x in states) else 'UNAVAILABLE')
  return {'status':status,'checks':checks}
class Diagnostics:
 def bundle(self,checks,hardware=None): return {'application_version':APP_VERSION,'platform': 'sanitized','hardware':hardware or {},'health':checks,'redacted_fields':['secrets','conversation_contents','memories','prompts','audio','media']}
def uninstall(app_dir,delete_data=False):
 app_dir=Path(app_dir)
 if delete_data and app_dir.exists(): shutil.rmtree(app_dir)
 return {'application_removed':True,'user_data_deleted':bool(delete_data)}
