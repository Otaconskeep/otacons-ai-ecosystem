from dataclasses import dataclass
from typing import Any
@dataclass
class ServiceAssignment:
 service_id: str; endpoint: str; model: str; placement: str
def resolve(deployment: Any, capability: str):
 candidates=[s for s in deployment.services if capability in s.capabilities or capability in s.required_capabilities]
 if not candidates: raise LookupError(f'No healthy service provides {capability}')
 s=candidates[0]; endpoint=s.endpoints[0].address if s.endpoints else s.metadata.get('endpoint','')
 return ServiceAssignment(s.id,endpoint,s.metadata.get('model',''),s.placement_resource_id)
