from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceAssignment:
    service_id: str
    endpoint: str
    model: str
    placement: str
    provider: str = ''
    defaults: dict | None = None


def resolve(deployment: Any, capability: str) -> ServiceAssignment:
    candidates = [
        s for s in deployment.services
        if capability in (s.capabilities or []) or capability in (s.required_capabilities or [])
    ]
    if not candidates:
        raise LookupError(f'No healthy service provides {capability}')
    s = candidates[0]
    endpoint = ''
    if s.endpoints:
        ep = s.endpoints[0]
        endpoint = getattr(ep, 'address', None) or (ep.get('address') if isinstance(ep, dict) else '') or ''
    meta = s.metadata or {}
    if not endpoint:
        endpoint = meta.get('endpoint', '')
    provider = meta.get('provider', '')
    defaults = meta.get('defaults') if isinstance(meta.get('defaults'), dict) else None
    return ServiceAssignment(
        s.id,
        endpoint,
        meta.get('model', ''),
        s.placement_resource_id,
        provider=provider,
        defaults=defaults,
    )
