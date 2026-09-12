"""Provider-neutral deployment topology model."""
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class Resource:
    id: str
    hostname: str | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Host(Resource):
    os: str | None = None
    architecture: str | None = None
    virtualization_provider: str | None = None
    cpu: dict[str, Any] = field(default_factory=dict)
    ram_gb: float | None = None
    storage: list[str] = field(default_factory=list)
    gpus: list[str] = field(default_factory=list)
    runtimes: list[str] = field(default_factory=list)
    virtual_machines: list[str] = field(default_factory=list)

@dataclass
class VirtualMachine(Resource):
    parent_host_id: str = ''
    hypervisor: str | None = None
    hypervisor_vm_id: str | None = None
    os: str | None = None
    cpu: dict[str, Any] = field(default_factory=dict)
    ram_gb: float | None = None
    runtimes: list[str] = field(default_factory=list)
    passthrough_devices: list[str] = field(default_factory=list)

@dataclass
class ContainerRuntime(Resource):
    parent_resource_id: str = ''
    runtime: str = 'docker'
    version: str | None = None
    storage_roots: list[str] = field(default_factory=list)

@dataclass
class Accelerator(Resource):
    parent_host_id: str = ''
    exposed_to: list[str] = field(default_factory=list)
    model: str = ''
    vram_gb: float = 0
    capability: str = 'GPU_SMALL'
    workload_capabilities: list[str] = field(default_factory=list)

@dataclass
class Storage(Resource):
    owner_resource_id: str = ''
    path: str = ''
    capacity_gb: float | None = None
    free_gb: float | None = None
    purpose: list[str] = field(default_factory=list)
    shared: bool = False
    network_mounted: bool = False
    execution_suitable: bool = True

@dataclass
class ServiceEndpoint:
    id: str
    service_id: str
    kind: str
    address: str
    health_url: str | None = None

@dataclass
class Service(Resource):
    service_type: str = ''
    placement_resource_id: str = ''
    runtime_id: str | None = None
    required_capabilities: list[str] = field(default_factory=list)
    endpoints: list[ServiceEndpoint] = field(default_factory=list)

@dataclass
class Deployment:
    id: str
    hosts: list[Host] = field(default_factory=list)
    virtual_machines: list[VirtualMachine] = field(default_factory=list)
    runtimes: list[ContainerRuntime] = field(default_factory=list)
    accelerators: list[Accelerator] = field(default_factory=list)
    storage: list[Storage] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    control_plane_resource_id: str | None = None

    def validate(self):
        ids = set()
        for group in (self.hosts, self.virtual_machines, self.runtimes, self.accelerators, self.storage, self.services):
            for item in group:
                if item.id in ids: raise ValueError(f'duplicate resource id: {item.id}')
                ids.add(item.id)
        host_ids = {x.id for x in self.hosts}; resource_ids = ids
        for vm in self.virtual_machines:
            if vm.parent_host_id not in host_ids: raise ValueError(f'VM parent missing: {vm.id}')
        for rt in self.runtimes:
            if rt.parent_resource_id not in resource_ids: raise ValueError(f'runtime parent missing: {rt.id}')
        for svc in self.services:
            if svc.placement_resource_id not in resource_ids: raise ValueError(f'service placement missing: {svc.id}')
        return True

    def as_dict(self):
        return asdict(self)
