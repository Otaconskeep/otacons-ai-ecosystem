import json
import unittest
from pathlib import Path
from core.topology import Deployment, Host, VirtualMachine, ContainerRuntime, Service

class TopologyTests(unittest.TestCase):
    def test_nested_reference_shape(self):
        raw=json.loads(Path('config/reference-topology.redacted.json').read_text())
        d=Deployment(id=raw['id'], hosts=[Host(**x) for x in raw['hosts']], virtual_machines=[VirtualMachine(**x) for x in raw['virtual_machines']], runtimes=[ContainerRuntime(**x) for x in raw['runtimes']], services=[Service(**x) for x in raw['services']])
        self.assertTrue(d.validate())
        self.assertEqual(d.virtual_machines[0].parent_host_id,'host_virtualization')
        self.assertEqual(d.services[1].runtime_id,'runtime_primary')
    def test_invalid_parent_rejected(self):
        d=Deployment('d', hosts=[Host('h')], virtual_machines=[VirtualMachine('v', parent_host_id='missing')])
        with self.assertRaises(ValueError): d.validate()

if __name__=='__main__': unittest.main()
