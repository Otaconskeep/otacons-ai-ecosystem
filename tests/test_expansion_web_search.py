"""web.search Instant Answer + HTML fallback + fail-loud on 0 hits."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from expansion.tools.web import web_search


class WebSearchCase(unittest.TestCase):
    def test_instant_answer_hits(self):
        payload = {
            'Heading': 'Python',
            'AbstractText': 'A programming language.',
            'AbstractURL': 'https://example.com/python',
            'RelatedTopics': [],
        }

        def _open(url, **kwargs):
            return json.dumps(payload), 'application/json'

        with mock.patch('expansion.tools.web._open', side_effect=_open):
            data, summary = web_search('python')
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['source'], 'duckduckgo_instant')
        self.assertEqual(len(data['results']), 1)
        self.assertIn('1 hits', summary)

    def test_html_fallback_when_instant_empty(self):
        html = (
            '<a class="result__a" href="https://duckduckgo.com/l/?uddg='
            'https%3A%2F%2Fexample.com%2Ftrends">24 Trends for 2026</a>'
            '<a class="result__snippet">Popular shirt designs</a>'
        )

        def _open(url, **kwargs):
            if 'api.duckduckgo.com' in url:
                return '{}', 'application/json'
            return html, 'text/html'

        with mock.patch('expansion.tools.web._open', side_effect=_open):
            data, summary = web_search('t-shirt design trends 2026')
        self.assertTrue(data.get('ok'), data)
        self.assertEqual(data['source'], 'duckduckgo_html')
        self.assertGreaterEqual(len(data['results']), 1)
        self.assertIn('example.com/trends', data['results'][0]['url'])
        self.assertIn('hits', summary)

    def test_zero_hits_marks_ok_false(self):
        def _open(url, **kwargs):
            if 'api.duckduckgo.com' in url:
                return '{}', 'application/json'
            return '<html><body>no results</body></html>', 'text/html'

        with mock.patch('expansion.tools.web._open', side_effect=_open):
            data, summary = web_search('zzzznonexistentquery999')
        self.assertFalse(data.get('ok'))
        self.assertEqual(data.get('error'), 'no search hits')
        self.assertEqual(data['results'], [])
        self.assertIn('0 hits', summary)


if __name__ == '__main__':
    unittest.main()
