"""Research deliverable dedupe + synthesis tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.research_deliverable import (
    build_research_markdown,
    dedupe_research_refs,
    is_chrome_snippet,
    maybe_export_to_desktop,
    write_research_deliverable,
)
from expansion.state_layout import resolve_layout


class ResearchDeliverableCase(unittest.TestCase):
    def test_dedupe_keeps_best_snippet(self):
        refs = [
            {'title': 'A', 'url': 'https://www.example.com/trends', 'snippet': 'Login/ Sign Up Cart Checkout'},
            {
                'title': 'Trends 2026',
                'url': 'https://example.com/trends',
                'snippet': 'Vintage washes and bold typography dominate apparel this year.',
            },
            {'title': 'A2', 'url': 'https://example.com/trends', 'snippet': 'short'},
        ]
        out = dedupe_research_refs(refs)
        self.assertEqual(len(out), 1)
        self.assertIn('Vintage washes', out[0]['snippet'])

    def test_chrome_detection(self):
        self.assertTrue(is_chrome_snippet('Login/ Sign Up Upgrade to PRO Mockups Cart Checkout'))
        self.assertFalse(is_chrome_snippet(
            'Printful charges a base cost per blank plus fulfillment; '
            'compare that against Etsy listing fees before choosing a POD partner.'
        ))

    def test_synthesis_answers_topics(self):
        refs = [
            {
                'title': '2026 shirt trends',
                'url': 'https://example.com/trends',
                'snippet': 'Bold typography and retro washes lead t-shirt design trends for 2026.',
            },
            {
                'title': 'POD fees',
                'url': 'https://example.com/fees',
                'snippet': 'Platform fees vary: Etsy takes a listing fee plus transaction cut; '
                           'Printful quotes base garment plus shipping.',
            },
        ]
        body, meta = build_research_markdown(
            request='What are 2026 design trends? What about platform fees?',
            job_id='job_test',
            agent='ledger',
            refs=refs,
        )
        self.assertTrue(meta['synthesis_ok'])
        self.assertIn('## Answers', body)
        self.assertNotIn('Next: turn sourced notes', body)
        self.assertIn('typography', body.lower())

    def test_desktop_export_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'job_x.md'
            src.write_text('# hi\n', encoding='utf-8')
            desk = Path(td) / 'Desktop'
            desk.mkdir()
            layout = resolve_layout()
            # Disabled by default
            self.assertIsNone(maybe_export_to_desktop(src, layout=layout, enabled=False))
            with mock.patch(
                'expansion.research_deliverable.resolve_user_desktop',
                return_value=desk,
            ):
                dest = maybe_export_to_desktop(src, layout=layout, enabled=True)
            self.assertTrue(dest)
            self.assertTrue(Path(dest).is_file())


if __name__ == '__main__':
    unittest.main()
