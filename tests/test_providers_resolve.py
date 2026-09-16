"""Ollama model resolution — prefer an installed tag over a stale config name."""
from __future__ import annotations

import unittest
from unittest import mock

from core.providers import OllamaProvider, ProviderError, TestProvider
from core.agent_service import chat
from core.deployment import local_deployment


class ResolveModelTests(unittest.TestCase):
    def test_exact_match(self):
        p = OllamaProvider()
        with mock.patch.object(p, 'list_models', return_value=['qwen2.5:7b', 'llama3:8b']):
            tag, note = p.resolve_model('qwen2.5:7b')
        self.assertEqual(tag, 'qwen2.5:7b')
        self.assertIsNone(note)

    def test_prefix_match(self):
        p = OllamaProvider()
        with mock.patch.object(p, 'list_models', return_value=['qwen2.5:7b-instruct-q4_K_M']):
            tag, note = p.resolve_model('qwen2.5:7b')
        self.assertEqual(tag, 'qwen2.5:7b-instruct-q4_K_M')
        self.assertIsNone(note)

    def test_fallback_when_missing(self):
        p = OllamaProvider()
        with mock.patch.object(p, 'list_models', return_value=['qwen2.5:7b', 'llama3:8b']):
            tag, note = p.resolve_model('qwen2.5:1.5b')
        self.assertEqual(tag, 'qwen2.5:7b')
        self.assertIn('1.5b', note)

    def test_empty_raises(self):
        p = OllamaProvider()
        with mock.patch.object(p, 'list_models', return_value=[]):
            with self.assertRaises(ProviderError):
                p.resolve_model('qwen2.5:7b')

    def test_chat_uses_fallback(self):
        class Fake(TestProvider):
            def resolve_model(self, requested):
                return 'qwen2.5:7b', 'fallback note'
            def generate(self, model, prompt):
                self.used = model
                return 'hi from ' + model

        d = local_deployment(llm_provider='test', llm_endpoint='test://', llm_model='qwen2.5:1.5b')
        fake = Fake()
        out = chat(d, {'id': 'agent_001', 'display_name': 'Aria'}, 'hello', provider=fake)
        self.assertEqual(out['model'], 'qwen2.5:7b')
        self.assertEqual(out['model_requested'], 'qwen2.5:1.5b')
        self.assertEqual(out['text'], 'hi from qwen2.5:7b')
        self.assertIn('fallback', out['model_note'])


if __name__ == '__main__':
    unittest.main()
