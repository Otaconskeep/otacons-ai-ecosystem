"""Research deliverable dedupe + synthesis + chrome + topic tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.research_deliverable import (
    build_research_markdown,
    dedupe_research_refs,
    extract_passages,
    extract_request_topics,
    is_chrome_snippet,
    maybe_export_to_desktop,
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
                'body': 'Vintage washes and bold typography dominate apparel this year. '
                        'Oversized fits remain strong across POD catalogs.',
            },
            {'title': 'A2', 'url': 'https://example.com/trends', 'snippet': 'short'},
        ]
        out = dedupe_research_refs(refs)
        self.assertEqual(len(out), 1)
        self.assertIn('Vintage washes', out[0].get('body') or out[0]['snippet'])

    def test_chrome_detection_production_shapes(self):
        printify = (
            'Catalog Pricing How it works How it works How Printify works Print on Demand 101 '
            'Resource Center Solutions Start selling Custom t-shirts Custom hoodies'
        )
        dtf = (
            'DTF Database Skip to content Home Suppliers Printers Tools Learn Blog About'
        )
        self.assertTrue(is_chrome_snippet(printify), printify)
        self.assertTrue(is_chrome_snippet(dtf), dtf)
        self.assertTrue(is_chrome_snippet('Login/ Sign Up Upgrade to PRO Mockups Apparel'))
        self.assertFalse(is_chrome_snippet(
            'Printful charges a base cost per blank plus fulfillment; '
            'compare that against Etsy listing fees before choosing a POD partner.'
        ))

    def test_extract_request_topics_multipart(self):
        req = (
            'Research t-shirt design trends for 2026, platform fees on Etsy and Printful, '
            'competitor strategy for small brands, and laser engraver / 3D printer integration.'
        )
        topics = extract_request_topics(req)
        self.assertGreaterEqual(len(topics), 3, topics)
        blob = ' '.join(topics).lower()
        self.assertTrue(any('trend' in t.lower() for t in topics) or 'trend' in blob)
        self.assertTrue(any('fee' in t.lower() or 'cost' in t.lower() for t in topics))
        self.assertTrue(any('competitor' in t.lower() for t in topics))
        self.assertTrue(any('laser' in t.lower() or '3d' in t.lower() for t in topics))

    def test_extract_passages_from_body(self):
        body = (
            'Skip to content Home Blog About. '
            'Bold typography and retro washes lead t-shirt design trends for 2026. '
            'Many sellers combine POD blanks with laser-engraved hang tags. '
            'Login Sign Up Cart Checkout Newsletter.'
        )
        passages = extract_passages(body, 'design trends 2026', limit=2)
        self.assertTrue(passages)
        self.assertTrue(any('typography' in p.lower() for p in passages))
        self.assertFalse(any('skip to content' in p.lower() for p in passages))

    def test_synthesis_answers_multiple_topics(self):
        refs = [
            {
                'title': '2026 shirt trends',
                'url': 'https://example.com/trends',
                'snippet': 'Bold typography.',
                'body': (
                    'Bold typography and retro washes lead t-shirt design trends for 2026. '
                    'Oversized fits remain popular in streetwear catalogs.'
                ),
            },
            {
                'title': 'POD fees',
                'url': 'https://example.com/fees',
                'snippet': 'Fees vary.',
                'body': (
                    'Etsy charges a listing fee plus a transaction percentage. '
                    'Printful quotes a base garment cost plus shipping and fulfillment.'
                ),
            },
            {
                'title': 'Laser tags',
                'url': 'https://example.com/laser',
                'body': (
                    'Small brands often pair print-on-demand shirts with laser-engraved '
                    'wooden hang tags and limited 3D-printed accessories.'
                ),
            },
        ]
        req = (
            'What are 2026 design trends? What about platform fees? '
            'How do competitors use laser engravers?'
        )
        with mock.patch('expansion.research_deliverable._llm_synthesize', return_value=None):
            body, meta = build_research_markdown(
                request=req,
                job_id='job_test',
                agent='ledger',
                refs=refs,
            )
        self.assertGreaterEqual(meta['topics'], 2, meta)
        self.assertGreaterEqual(meta['answered_topics'], 2, meta)
        self.assertTrue(meta['synthesis_ok'], meta)
        self.assertIn('## Answers', body)
        self.assertNotIn('Next: turn sourced notes', body)
        self.assertEqual(meta['synthesis_source'], 'extractive')

    def test_desktop_export_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'job_x.md'
            src.write_text('# hi\n', encoding='utf-8')
            desk = Path(td) / 'Desktop'
            desk.mkdir()
            layout = resolve_layout()
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
