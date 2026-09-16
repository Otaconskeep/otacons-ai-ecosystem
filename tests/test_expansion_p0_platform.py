"""P0 platform tests: state layout, topology, versions, migrations, manifest,
events, provision, readiness, dossier/vulnerabilities, relationship graph.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.dossier import (
    LivingDossier, ObservedTrait, empty_canonical_dossier,
    validate_canonical_dossier, validate_living_dossier,
)
from expansion.events import EVENT_TYPES, EventBus, new_event
from expansion.manifest import (
    ALLOWED_AEAD, ArtifactRef, PackageManifest, build_dev_manifest,
    from_dict as manifest_from_dict, save_manifest, to_dict as manifest_to_dict,
    verify_artifact_hashes,
)
from expansion.migrations import apply_pending, load_ledger, pending_migrations, snapshot_user_state
from expansion.provision import PROVISION_STEPS, provision_agent, provision_default_roster
from expansion.readiness import ReadinessState, evaluate_foundation
from expansion.relationship_graph import (
    RELATIONSHIP_DIMENSIONS, apply_dimension_delta, new_directional,
)
from expansion.seed_defaults import build_default_roster, seed
from expansion.state_layout import resolve_layout
from expansion.topology import (
    default_topology, public_core_install_present, save_topology,
    shell_public_install_probe,
)
from expansion.versions import EXPANSION_VERSION, current_versions, save_installed_versions
from expansion.vulnerabilities import (
    Vulnerability, VulnerabilityKind, VulnerabilityProfile,
    validate_vulnerability_profile,
)


class LayoutTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
        }
        self._cm = mock.patch.dict(os.environ, self.env, clear=False)
        self._cm.start()

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def layout(self):
        return resolve_layout(product_root=Path(__file__).resolve().parents[1] / 'expansion')


class TestStateLayout(LayoutTestCase):
    def test_user_and_product_roots_are_distinct(self):
        layout = self.layout()
        self.assertNotEqual(layout.product_root, layout.user_data_root)
        self.assertTrue(str(layout.user_agents).endswith('agents'))
        layout.ensure_user_dirs()
        self.assertTrue(layout.user_events.is_dir())
        self.assertTrue(layout.user_migrations.is_dir())

    def test_product_write_guard(self):
        layout = self.layout()
        with self.assertRaises(PermissionError):
            layout.assert_not_product_write(layout.product_agents / 'x.json')


class TestTopology(LayoutTestCase):
    def test_default_topology_has_no_private_keep_ips(self):
        cfg = default_topology()
        self.assertEqual(cfg.validate(), [])
        self.assertIn('127.0.0.1', cfg.ollama_url)

    def test_rejects_private_keep_fragments(self):
        cfg = default_topology()
        cfg.ollama_url = 'http://192.168.50.219:11434'
        self.assertTrue(any('forbidden' in e for e in cfg.validate()))

    def test_public_install_probe_excludes_opt_otacon(self):
        probe = shell_public_install_probe()
        self.assertNotIn('/opt/otacon', probe)
        self.assertIn('otacon-ai-ecosystem}/core', probe)

    def test_public_core_install_ignores_private_keep_path(self):
        markers = public_core_install_present(home=self.root, install_dir=self.root / 'missing')
        self.assertTrue(markers['private_keep_path_ignored'])
        self.assertFalse(markers['any_public_marker'])

    def test_save_topology_roundtrip(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        path = save_topology(default_topology(), layout.user_preferences / 'topology.json')
        self.assertTrue(path.is_file())


class TestVersionsAndManifest(LayoutTestCase):
    def test_current_versions_include_expansion(self):
        v = current_versions()
        self.assertEqual(v.expansion_version, EXPANSION_VERSION)
        self.assertGreaterEqual(v.agent_schema, 1)

    def test_save_versions(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        path = save_installed_versions(path=layout.user_config_root / 'versions.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['expansion_version'], EXPANSION_VERSION)

    def test_dev_manifest_validates(self):
        m = build_dev_manifest()
        self.assertEqual(m.validate(), [])
        self.assertEqual(m.channel, 'dev')

    def test_protected_manifest_requires_signature(self):
        m = build_dev_manifest()
        m.channel = 'protected'
        self.assertTrue(any('signature' in e for e in m.validate()))

    def test_encrypted_artifact_requires_allowed_aead(self):
        m = build_dev_manifest(artifacts=[
            ArtifactRef(path='x.bin', sha256='a' * 64, role='encrypted_bundle',
                        encrypted=True, aead='TOTALLY-FAKE'),
        ])
        self.assertTrue(any('aead' in e for e in m.validate()))
        m.artifacts[0].aead = ALLOWED_AEAD[0]
        # still missing protected signature if channel protected — keep channel=dev
        self.assertEqual(m.validate(), [])

    def test_manifest_rejects_embedded_key_material(self):
        m = build_dev_manifest()
        m.encryption = {'aead': 'AES-256-GCM', 'key': 'secret'}
        self.assertTrue(any('key' in e for e in m.validate()))

    def test_manifest_roundtrip_and_hash_verify(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        blob = layout.user_config_root / 'artifact.txt'
        blob.write_text('hello', encoding='utf-8')
        import hashlib
        digest = hashlib.sha256(b'hello').hexdigest()
        m = build_dev_manifest(artifacts=[
            ArtifactRef(path='artifact.txt', sha256=digest, role='asset'),
        ])
        path = save_manifest(m, layout.user_config_root / 'PACKAGE_MANIFEST.dev.json')
        loaded = manifest_from_dict(manifest_to_dict(m))
        self.assertEqual(loaded.expansion_version, m.expansion_version)
        self.assertEqual(verify_artifact_hashes(loaded, layout.user_config_root), [])
        self.assertTrue(path.is_file())


class TestMigrations(LayoutTestCase):
    def test_baseline_migration_applies_once(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        self.assertTrue(pending_migrations(layout))
        plan = apply_pending(layout)
        self.assertTrue(any(r['migration_id'] == 'm000_baseline' for r in plan.applied))
        self.assertEqual(pending_migrations(layout), [])
        # idempotent
        apply_pending(layout)
        ledger = load_ledger(layout)
        self.assertEqual(sum(1 for r in ledger.applied if r['migration_id'] == 'm000_baseline'), 1)

    def test_snapshot_user_state(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        (layout.user_agents / 'note.txt').write_text('x', encoding='utf-8')
        snap = snapshot_user_state(layout, label='test')
        self.assertTrue((snap / 'SNAPSHOT.json').is_file())


class TestEvents(LayoutTestCase):
    def test_emit_and_persist(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        bus = EventBus(layout=layout, persist=True)
        seen = []
        bus.subscribe(lambda e: seen.append(e.event_type), 'agent.message')
        ev = bus.emit(new_event('agent.message', actor='aria', subject='user', payload={'text': 'hi'}))
        self.assertEqual(ev.validate(), [])
        self.assertEqual(seen, ['agent.message'])
        self.assertTrue((layout.user_events / 'events.jsonl').is_file())
        self.assertGreaterEqual(len(bus.recent()), 1)

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(ValueError):
            EventBus(layout=self.layout(), persist=False).emit(
                new_event('not.a.real.event')
            )

    def test_catalog_includes_locked_types(self):
        for t in ('job.created', 'relationship.changed', 'emotion.changed',
                  'memory.created', 'journal.created', 'diary.created'):
            self.assertIn(t, EVENT_TYPES)


class TestProvision(LayoutTestCase):
    def test_provision_steps_are_fifteen(self):
        self.assertEqual(len(PROVISION_STEPS), 15)

    def test_provision_aria(self):
        layout = self.layout()
        aria = build_default_roster()[0]
        tx = provision_agent(aria, layout=layout)
        self.assertEqual(tx.status, 'completed')
        self.assertEqual(len(tx.steps), 15)
        self.assertTrue((layout.user_agents / 'default-aria.json').is_file())

    def test_provision_default_roster(self):
        layout = self.layout()
        txs = provision_default_roster(layout=layout)
        self.assertEqual(len(txs), 5)
        self.assertTrue(all(t.status == 'completed' for t in txs))
        report = evaluate_foundation(layout)
        self.assertTrue(report.foundation_ready())
        self.assertEqual(report.semantic['agents_load'], ReadinessState.READY)
        self.assertEqual(report.semantic['registry_validates'], ReadinessState.READY)


class TestReadiness(LayoutTestCase):
    def test_empty_layout_not_foundation_ready(self):
        layout = self.layout()
        layout.ensure_user_dirs()
        report = evaluate_foundation(layout)
        self.assertFalse(report.foundation_ready())

    def test_seed_then_foundation_ready(self):
        layout = self.layout()
        self.assertEqual(seed(layout.user_agents), 0)
        report = evaluate_foundation(layout)
        self.assertTrue(report.foundation_ready())


class TestDossierAndVulnerabilities(unittest.TestCase):
    def test_empty_canonical_valid(self):
        d = empty_canonical_dossier('aria', display_name='Aria')
        self.assertEqual(validate_canonical_dossier(d), [])

    def test_vulnerability_cannot_impair_operations(self):
        p = VulnerabilityProfile(items=(
            Vulnerability(kind=VulnerabilityKind.FEAR.value, label='failure', intensity=0.4,
                          affects_operations=True),
        ))
        self.assertTrue(any('operational' in e.lower() or 'affects_operations' in e
                            for e in validate_vulnerability_profile(p)))

    def test_living_dossier_requires_provenance(self):
        living = LivingDossier(
            schema_version=1,
            agent_id='vector',
            observed_traits=(ObservedTrait(trait='affinity_infra', value='high',
                                           confidence=0.8, evidence_event_ids=()),),
        )
        self.assertTrue(any('evidence' in e for e in validate_living_dossier(living)))


class TestRelationshipGraph(unittest.TestCase):
    def test_directional_not_symmetric(self):
        a2m = new_directional('aria', 'muse')
        m2a = new_directional('muse', 'aria')
        self.assertNotEqual(a2m.dimensions['jealousy'], m2a.dimensions['jealousy'])
        self.assertEqual(set(a2m.dimensions), set(RELATIONSHIP_DIMENSIONS))

    def test_delta_requires_event_provenance(self):
        rel = new_directional('aria', 'ledger')
        with self.assertRaises(ValueError):
            apply_dimension_delta(rel, {'trust': 0.05}, event_id='')
        apply_dimension_delta(rel, {'trust': 0.05}, event_id='evt_test')
        self.assertIn('evt_test', rel.provenance_event_ids)

    def test_no_self_relationship(self):
        with self.assertRaises(ValueError):
            new_directional('aria', 'aria')


class TestProbeFiles(unittest.TestCase):
    def test_windows_assistant_probe_has_no_opt_otacon(self):
        text = Path('/root/otacons-ai-ecosystem/deploy/windows-setup-assistant.ps1').read_text(encoding='utf-8')
        start = text.index('function Test-OtaconFiles')
        end = text.index('function Test-OtaconService')
        block = text[start:end]
        # Strip comments; the live probe command must not test /opt/otacon.
        code_lines = [ln for ln in block.splitlines() if not ln.strip().startswith('#')]
        code = '\n'.join(code_lines)
        self.assertNotIn('/opt/otacon', code)
        self.assertNotIn('`$HOME/otacon"', code)
        self.assertIn('otacon-ai-ecosystem', code)

    def test_wake_script_has_no_opt_otacon(self):
        text = Path('/root/otacons-ai-ecosystem/deploy/wake-otacon.ps1').read_text(encoding='utf-8')
        code_lines = [ln for ln in text.splitlines() if not ln.strip().startswith('#')]
        code = '\n'.join(code_lines)
        self.assertNotIn('test -d /opt/otacon', code)
        self.assertNotIn('"$HOME/otacon"', code)
        self.assertIn('otacon-ai-ecosystem}/core', code)


if __name__ == '__main__':
    unittest.main()
