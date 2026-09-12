"""Portable Beta Gate 1 reporting and aggregation; performs no implicit hardware tests."""
from __future__ import annotations
from dataclasses import dataclass
import json, platform
APP_VERSION='0.1.0'; SCHEMA_VERSION=1
REQUIRED=('REAL_OLLAMA_INFERENCE_PASS','REAL_MEMORY_INFERENCE_PASS','REAL_TTS_ACCEPTANCE_PASS','REAL_STT_ACCEPTANCE_PASS','REAL_RESOURCE_ACCEPTANCE_PASS','NATIVE_GUI_ACCEPTANCE_PASS','PHYSICAL_MICROPHONE_ACCEPTANCE_PASS','PHYSICAL_SPEAKER_ACCEPTANCE_PASS','REAL_LOCAL_VOICE_LOOP_PASS')
def report(mode, statuses, *, commit, confirmations=None, failures=None, evidence=None):
 allowed={k:v for k,v in statuses.items() if k in REQUIRED and v in ('PASS','PENDING','FAIL')}; confirmations=confirmations or {}; failures=failures or {}
 for k,v in confirmations.items():
  if v is True and k in REQUIRED: allowed[k]='PASS'
 return {'schema_version':SCHEMA_VERSION,'app_version':APP_VERSION,'commit':commit,'mode':mode,'statuses':allowed,'confirmations':{k:bool(v) for k,v in confirmations.items() if k in REQUIRED},'evidence':evidence or {},'failures':{k:'SANITIZED_PROVIDER_FAILURE' for k,v in failures.items() if k in REQUIRED},'result':'PASS' if all(allowed.get(k)=='PASS' for k in REQUIRED) else 'PARTIAL'}
def merge(reports):
 if not reports:return {'result':'PENDING','reason':'NO_REPORTS'}
 builds={(r.get('app_version'),r.get('commit')) for r in reports}
 if len(builds)!=1:return {'result':'FAIL','reason':'MISMATCHED_PUBLIC_BUILD'}
 statuses={}
 for k in REQUIRED:
  vals=[r.get('statuses',{}).get(k,'PENDING') for r in reports]; statuses[k]='PASS' if 'PASS' in vals else ('FAIL' if 'FAIL' in vals else 'PENDING')
 return {'schema_version':SCHEMA_VERSION,'app_version':reports[0]['app_version'],'commit':reports[0]['commit'],'reports':len(reports),'statuses':statuses,'result':'PASS' if all(v=='PASS' for v in statuses.values()) else 'PARTIAL'}
def save(data,path): open(path,'w').write(json.dumps(data,indent=2)+'\n')
