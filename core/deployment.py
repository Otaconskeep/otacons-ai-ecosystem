"""Deployment helpers for local/sandbox graphs (no hardcoding inside AgentService)."""
from __future__ import annotations

import os
from typing import Any

from core.topology import Deployment, Host, Service, ServiceEndpoint


def llm_test_deployment(endpoint: str = 'test://', model: str = 'chat_small') -> Deployment:
    svc = Service(
        id='service_llm_test',
        service_type='llm',
        placement_resource_id='host_local',
        capabilities=['conversational_llm'],
        required_capabilities=['conversational_llm'],
        metadata={'endpoint': endpoint, 'model': model, 'provider': 'test'},
        endpoints=[ServiceEndpoint('ep_llm_test', 'service_llm_test', 'http', endpoint)],
    )
    return Deployment('deployment_local', [Host('host_local')], services=[svc])


def tts_service(
    *,
    service_id: str = 'service_tts_001',
    endpoint: str | None = None,
    provider: str | None = None,
    defaults: dict | None = None,
    placement: str = 'host_local',
) -> Service:
    """Represent TTS as a normal Service resource.

    Endpoint/provider come from config/env — never from AgentService hardcoding.
    """
    provider = provider or os.getenv('OTACON_TTS_PROVIDER', 'test')
    if endpoint is None:
        endpoint = os.getenv('OTACON_TTS_ENDPOINT', 'test://tts')
    defaults = defaults or {
        'length_scale': float(os.getenv('OTACON_TTS_DEFAULT_LENGTH_SCALE', '1.25')),
        'noise_scale': float(os.getenv('OTACON_TTS_DEFAULT_NOISE_SCALE', '0.95')),
        'noise_w': float(os.getenv('OTACON_TTS_DEFAULT_NOISE_W', '0.95')),
    }
    kind = 'wyoming' if str(endpoint).startswith(('wyoming://', 'tcp://')) or provider == 'piper' else 'test'
    return Service(
        id=service_id,
        service_type='tts',
        placement_resource_id=placement,
        capabilities=['text_to_speech'],
        required_capabilities=['text_to_speech'],
        metadata={
            'endpoint': endpoint,
            'provider': provider,
            'defaults': defaults,
            'health': 'UNKNOWN',
        },
        endpoints=[ServiceEndpoint(f'ep_{service_id}', service_id, kind, endpoint)],
    )


def local_deployment(
    *,
    include_llm: bool = True,
    include_tts: bool = True,
    tts_endpoint: str | None = None,
    tts_provider: str | None = None,
    tts_defaults: dict | None = None,
) -> Deployment:
    services: list[Service] = []
    if include_llm:
        services.append(
            Service(
                id='service_llm_test',
                service_type='llm',
                placement_resource_id='host_local',
                capabilities=['conversational_llm'],
                required_capabilities=['conversational_llm'],
                metadata={'endpoint': 'test://', 'model': 'chat_small', 'provider': 'test'},
                endpoints=[ServiceEndpoint('ep_llm_test', 'service_llm_test', 'http', 'test://')],
            )
        )
    if include_tts:
        services.append(
            tts_service(endpoint=tts_endpoint, provider=tts_provider, defaults=tts_defaults)
        )
    return Deployment('deployment_local', [Host('host_local')], services=services)


def merge_tts_into_deployment(deployment: Deployment, **kwargs: Any) -> Deployment:
    """Ensure a TTS service is registered on an existing deployment graph."""
    has = any(
        'text_to_speech' in (s.capabilities or []) or 'text_to_speech' in (s.required_capabilities or [])
        for s in deployment.services
    )
    if not has:
        deployment.services.append(tts_service(**kwargs))
    return deployment
