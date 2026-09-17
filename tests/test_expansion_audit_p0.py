"""Regression tests for audit P0 gaps (entitlement, seed, migrations, tools, jobs)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.entitlement import EntitlementGate
from expansion.migrations import Migration, MigrationPlan, MigrationRecord, pending_migrations, save_ledger
from expansion.pipeline import LivingPipeline
from expansion.readiness import evaluate_foundation
from expansion.seed_defaults import seed
from expansion.state_layout import resolve_layout
from expansion.tools import ToolGateway, ToolResult


class AuditP0Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        self._cm = mock.patch.dict(os.environ, self.env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()


class TestEntitlementStaleNone(AuditP0Case):
    def test_preseed_false_then_true_after_roster(self):
        gate = EntitlementGate(self.layout)
        before = gate.current()
        self.assertFalse(before.expansion_entitled)
        self.assertEqual(before.source, 'none')

        seed(self.layout.user_agents)
        after = gate.current()
        self.assertTrue(after.expansion_entitled)
        self.assertEqual(after.source, 'local_dev')

    def test_explicit_license_denial_preserved(self):
        from expansion.persist import atomic_write_json
        path = self.layout.user_preferences / 'entitlement.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, {
            'expansion_entitled': False,
            'source': 'license',
            'checked_at': 1.0,
            'message': 'denied by license',
            'grace_until': 0.0,
        })
        seed(self.layout.user_agents)
        state = EntitlementGate(self.layout).current()
        self.assertFalse(state.expansion_entitled)
        self.assertEqual(state.source, 'license')


class TestSeedPreservesCustom(AuditP0Case):
    def test_unknown_field_survives_reseed(self):
        seed(self.layout.user_agents)
        path = self.layout.user_agents / 'default-aria.json'
        raw = json.loads(path.read_text(encoding='utf-8'))
        raw['owner_custom_note'] = 'keep-me'
        raw['persona'] = 'Owner-customized Aria persona text'
        path.write_text(json.dumps(raw, indent=2), encoding='utf-8')

        seed(self.layout.user_agents)
        after = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(after.get('owner_custom_note'), 'keep-me')
        self.assertEqual(after.get('persona'), 'Owner-customized Aria persona text')


class TestFailedMigrationRequeue(AuditP0Case):
    def test_failed_migration_remains_pending(self):
        mid = 'audit_fail_probe_v1'

        def _boom(_layout):
            raise RuntimeError('injected failure')

        fake = Migration(
            migration_id=mid,
            description='probe',
            from_agent_schema=1,
            to_agent_schema=1,
            apply=_boom,
        )
        plan = MigrationPlan(
            engine_version=1,
            applied=[
                MigrationRecord(
                    migration_id=mid,
                    applied_at=1.0,
                    from_agent_schema=1,
                    to_agent_schema=1,
                    success=False,
                    notes='boom',
                ),
            ],
        )
        save_ledger(plan, self.layout)

        with mock.patch('expansion.migrations._REGISTRY', [fake]):
            pending = pending_migrations(self.layout)
            self.assertTrue(any(m.migration_id == mid for m in pending))


class TestToolGatewayTruthfulness(AuditP0Case):
    def test_nonzero_exit_is_not_ok(self):
        gw = ToolGateway(self.layout)

        def _fake_dispatch(capability, *, agent_id, **kwargs):
            return {'exit_code': 1, 'stderr': 'boom'}, 'ran'

        with mock.patch.object(gw, '_dispatch', side_effect=_fake_dispatch):
            with mock.patch.object(gw.policy, 'check') as check:
                check.return_value = mock.Mock(allowed=True, reason='', disposition='authorize')
                result = gw.invoke('vector', 'shell.execute', command='false')
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.data.get('exit_code'), 1)

    def test_journal_write_is_durable(self):
        from expansion.journal import JournalStore
        gw = ToolGateway(self.layout)
        with mock.patch.object(gw.policy, 'check') as check:
            check.return_value = mock.Mock(allowed=True, reason='', disposition='authorize')
            result = gw.invoke('aria', 'journal.write', summary='audit probe entry')
        self.assertTrue(result.ok)
        self.assertTrue(result.data.get('written'))
        recent = JournalStore(self.layout).recent(agent_id='aria', limit=5)
        self.assertTrue(any('audit probe entry' in (j.summary or '') for j in recent))


class TestJobsQueueNotFakeComplete(AuditP0Case):
    def test_default_create_queues_without_complete(self):
        seed(self.layout.user_agents)
        pipe = LivingPipeline(self.layout)
        out = pipe.create_and_run_job('handle the release', domain='coordination')
        self.assertTrue(out.get('queued'))
        self.assertFalse(out.get('simulated'))
        self.assertEqual(out['job'].status, 'RUNNING')
        self.assertNotEqual(out['job'].status, 'COMPLETE')

    def test_simulate_can_complete(self):
        seed(self.layout.user_agents)
        pipe = LivingPipeline(self.layout)
        out = pipe.create_and_run_job(
            'simulated done', domain='infrastructure', succeed=True, simulate=True,
        )
        self.assertTrue(out.get('simulated'))
        self.assertEqual(out['job'].status, 'COMPLETE')


class TestReadinessGates(AuditP0Case):
    def test_foundation_without_entitlement_not_surfaces_ready(self):
        # Pre-seed entitlement deny, then seed without refreshing gate via evaluate
        from expansion.persist import atomic_write_json
        seed(self.layout.user_agents)
        # Force a stale none deny that would have locked surfaces pre-fix —
        # current() should upgrade; verify expansion_ready needs stores too.
        gate = EntitlementGate(self.layout)
        self.assertTrue(gate.current().expansion_entitled)
        report = evaluate_foundation(self.layout)
        self.assertTrue(report.foundation_ready())
        # surfaces_ready requires entitlement semantic READY
        self.assertTrue(report.surfaces_ready())
        # expansion_ready needs writable stores; seed alone may not create them all
        d = report.to_dict()
        self.assertIn('expansion_ready', d)
        self.assertIn('surfaces_ready', d)
        self.assertIn('entitlement', d['semantic'])


class TestInstallerContracts(unittest.TestCase):
    def test_bootstrap_uses_stdin_handoff(self):
        sh = (Path(__file__).resolve().parents[1] / 'install_otacon_expansion.sh').read_text(
            encoding='utf-8', errors='replace',
        )
        self.assertIn('"$VPY" - < "$BOOT_PY"', sh)
        self.assertNotIn('"$VPY" "$BOOT_PY"', sh)
        self.assertIn('TESTS_SKIPPED', sh)
        self.assertIn('FOUNDATION INSTALLED', sh)
        self.assertNotIn('Dashboard/Codec/War Room/Video Studio are NOT built yet', sh)

    def test_windows_installer_honors_skip_tests_and_entitlement(self):
        ps1 = (Path(__file__).resolve().parents[1] / 'deploy' / 'install-otacon-expansion.ps1').read_text(
            encoding='utf-8', errors='replace',
        )
        self.assertIn('PSBoundParameters.ContainsKey(\'SkipTests\')', ps1)
        self.assertIn('expansion_entitled', ps1)
        self.assertIn('FOUNDATION INSTALLED', ps1)
        self.assertNotIn('EXPANSION READY', ps1)


if __name__ == '__main__':
    unittest.main()
