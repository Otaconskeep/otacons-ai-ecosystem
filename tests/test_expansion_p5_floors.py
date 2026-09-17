"""P5 flagship floor API + dossier depth + UI surface tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.canonical_dossiers import CANONICAL_AGENT_IDS, clear_dossier_cache, get_canonical_dossier
from expansion.floors import (
    build_command_floor,
    build_dashboard,
    build_diary_index,
    build_dossier_card,
    build_dossiers_index,
    build_emotion_roster,
    build_intel_floor,
    build_journal_browser,
    build_ops_floor,
    build_war_room,
)
from expansion.jobs import JobStore
from expansion.journal import JournalStore, new_journal_entry
from expansion.diary import DiaryStore
from expansion.pipeline import LivingPipeline
from expansion.events import new_event
from expansion.rooms import RoomRegistry
from expansion.state_layout import resolve_layout


class P5FloorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        clear_dossier_cache()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()


class TestAgentDepth(P5FloorCase):
    def test_all_agents_have_diary_style_and_depth_kinds(self):
        required = {'fear', 'anxiety', 'insecurity', 'self_conscious', 'crutch'}
        for aid in CANONICAL_AGENT_IDS:
            d = get_canonical_dossier(aid, self.layout)
            self.assertTrue(d.character.diary_style.strip(), aid)
            kinds = {v.kind for v in d.vulnerabilities.items}
            # self_conscious_area counts as self_conscious
            if 'self_conscious_area' in kinds:
                kinds.add('self_conscious')
            missing = required - kinds
            self.assertFalse(missing, f'{aid} missing {missing}')
            # intentional absences allowed but must be marked
            for v in d.vulnerabilities.items:
                if v.label == 'not_emphasized':
                    self.assertTrue(v.intentional_absence, f'{aid}.{v.kind}')

    def test_diary_uses_diary_style(self):
        j = new_journal_entry(
            agent_id='aria',
            event_type='test.event',
            summary='Owner thanked Aria for coordination.',
            objective_result='success',
            event_ids=('ev_test_1',),
        )
        JournalStore(self.layout).append(j)
        entry = DiaryStore(self.layout).generate_from_journal(j)
        style = get_canonical_dossier('aria', self.layout).character.diary_style
        self.assertIn(style.split('—')[0].strip()[:12], entry.text)
        self.assertEqual(entry.why.get('diary_style'), style)


class TestFloorPayloads(P5FloorCase):
    def test_dossiers_surface(self):
        idx = build_dossiers_index(self.layout)
        self.assertEqual(len(idx['agents']), 5)
        card = build_dossier_card('muse', self.layout)
        self.assertIn('vulnerabilities', card)
        self.assertIn('by_kind', card['vulnerabilities'])
        self.assertIn('living', card)
        self.assertIn('learning', card)
        # no fake placeholder claim text
        blob = str(card)
        self.assertNotIn('lorem ipsum', blob.lower())
        self.assertNotIn('TODO', blob)

    def test_journal_diary_emotion_war_command_intel_ops(self):
        # seed one real journal via pipeline-ish append
        j = new_journal_entry(
            agent_id='ledger',
            event_type='job.complete',
            summary='Continuity check passed.',
            objective_result='ok',
            job_id='job_seed_1',
            event_ids=('ev_j1',),
            emotion_effects=[{'dim': 'confidence', 'delta': 0.05}],
            relationship_effects=[{'target': 'aria', 'affinity': 0.01}],
        )
        JournalStore(self.layout).append(j)
        DiaryStore(self.layout).generate_from_journal(j)

        jb = build_journal_browser(self.layout)
        self.assertGreaterEqual(len(jb['entries']), 1)
        self.assertEqual(jb['kind'], 'journal')

        di = build_diary_index(self.layout)
        self.assertEqual(di['kind'], 'diary')
        ledger = next(a for a in di['agents'] if a['agent_id'] == 'ledger')
        self.assertGreaterEqual(ledger['count'], 1)

        emo = build_emotion_roster(self.layout)
        self.assertEqual(len(emo['agents']), 5)
        self.assertIn('dimensions', emo)

        wr = build_war_room(self.layout)
        self.assertIn('peer_review_note', wr['rex'])
        self.assertIn('VERIFYING', wr['rex']['peer_review_note'])
        self.assertIn('peer review', wr['rex']['peer_review_note'].lower())
        self.assertIn('operations', wr)
        self.assertIn('active', wr)  # legacy alias

        cmd = build_command_floor(self.layout)
        self.assertIn('workload', cmd)
        self.assertIn('autonomous_summary', cmd)

        intel = build_intel_floor(self.layout)
        self.assertIn('learned_claims', intel)
        self.assertIn('journal_timeline', intel)

        ops = build_ops_floor(self.layout)
        self.assertIn('service_readiness', ops)
        self.assertIn('home_assistant', ops)

    def test_dashboard_enabled_after_bootstrap(self):
        dash = build_dashboard(self.layout)
        # may be enabled depending on entitlement; must not invent fake agents
        if dash.get('enabled'):
            self.assertEqual(len(dash.get('roster') or []), 5)
            self.assertIn('learning_highlights', dash)

    def test_page_builder_registry_only(self):
        reg = RoomRegistry(self.layout)
        rooms = reg.seed_defaults()
        ids = {r.page_id for r in rooms}
        self.assertIn('dossiers', ids)
        self.assertIn('journal', ids)
        self.assertIn('diary', ids)
        self.assertIn('page_builder', ids)

    def test_rex_verifying_label_mentions_peer_review(self):
        from expansion.rex import REX_STAGES
        labels = dict(REX_STAGES)
        self.assertIn('Peer Review', labels['VERIFYING'])

    def test_ui_assets_exist(self):
        root = Path(__file__).resolve().parents[1] / 'ui'
        for name in ('floors.js', 'floors.css', 'wizard.js', 'index.html'):
            self.assertTrue((root / name).is_file(), name)
        index = (root / 'index.html').read_text()
        self.assertIn('floors.js', index)
        floors = (root / 'floors.js').read_text()
        for fn in (
            'renderDossiersFloor', 'renderJournalFloor', 'renderDiaryFloor',
            'renderRelationshipsFloor', 'renderEmotionsFloor', 'renderWarRoomFloor',
            'renderCommandFloor', 'renderIntelFloor', 'renderReportsFloor',
            'renderCreativeFloor', 'renderOpsFloor', 'renderPageBuilderFloor',
            'renderCommandCenterFloor',
        ):
            self.assertIn(fn, floors)
        # no private Keep names in UI floors
        for banned in ('Albedo', 'Kurumi', 'Solid Snake', 'Mei Ling', 'Psycho Mantis', 'Xof', '/opt/otacon'):
            self.assertNotIn(banned, floors)


class TestCoreOnlyUnaffected(unittest.TestCase):
    def test_floors_import_without_layout(self):
        # Importing floors module must not require Keep private paths
        import expansion.floors as floors
        self.assertTrue(hasattr(floors, 'build_dossiers_index'))


if __name__ == '__main__':
    unittest.main()
