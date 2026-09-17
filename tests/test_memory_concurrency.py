"""Concurrency regressions for MemoryStore under threaded HTTP use."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import ThreadingHTTPServer
from pathlib import Path

from core.memory import MemoryStore
from installer import server as server_mod


class MemoryThreadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'runtime' / 'memory.sqlite'
        self.store = MemoryStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_create_conversation_from_many_threads(self):
        n = 32
        errors = []
        ids = []

        def worker(i):
            try:
                cid = self.store.create_conversation(f'u{i % 4}', 'agent_001', title=f't{i}')
                self.store.append(cid, f'u{i % 4}', 'agent_001', 'user', f'hello {i}')
                self.store.remember(f'u{i % 4}', 'agent_001', f'fact-{i}', cid)
                msgs = self.store.messages(cid)
                self.assertEqual(len(msgs), 1)
                return cid
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')
                raise

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(worker, i) for i in range(n)]
            for fut in as_completed(futures):
                ids.append(fut.result())

        self.assertEqual(len(errors), 0, errors)
        self.assertEqual(len(ids), n)
        self.assertEqual(len(set(ids)), n)
        # No ProgrammingError / shared-connection symptom in any path.
        blob = ' '.join(errors).lower()
        self.assertNotIn('programmingerror', blob)
        self.assertNotIn('same thread', blob)

    def test_concurrent_read_write_same_user(self):
        cid = self.store.create_conversation('u1', 'agent_001')
        barrier = threading.Barrier(8)
        errors = []

        def writer(i):
            barrier.wait(timeout=5)
            try:
                self.store.append(cid, 'u1', 'agent_001', 'user', f'msg-{i}')
                self.store.remember('u1', 'agent_001', f'mem-{i}', cid)
                _ = self.store.list_memories('u1', 'agent_001')
                _ = self.store.messages(cid, limit=50)
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(self.store.messages(cid, limit=50)), 8)


class ThreadedChatHttpTests(unittest.TestCase):
    """Spin ThreadingHTTPServer and hammer /api/chat_with_agent concurrently."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / 'runtime').mkdir(parents=True, exist_ok=True)
        cls._prev_memory = server_mod.MEMORY
        cls._prev_config = server_mod.CONFIG_ROOT
        cls._prev_env = os.environ.get('OTACON_USE_TEST_LLM')
        os.environ['OTACON_USE_TEST_LLM'] = '1'
        server_mod.CONFIG_ROOT = root
        server_mod.MEMORY = MemoryStore(root / 'runtime' / 'memory.sqlite')
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server_mod.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server_mod.MEMORY = cls._prev_memory
        server_mod.CONFIG_ROOT = cls._prev_config
        if cls._prev_env is None:
            os.environ.pop('OTACON_USE_TEST_LLM', None)
        else:
            os.environ['OTACON_USE_TEST_LLM'] = cls._prev_env
        cls.tmp.cleanup()

    def _post_chat(self, message: str, user_id: str) -> dict:
        body = json.dumps({
            'message': message,
            'agent_id': 'agent_001',
            'user_id': user_id,
            'auto_speak': False,
        }).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.port}/api/chat_with_agent',
            data=body,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def test_concurrent_chat_requests_no_sqlite_thread_error(self):
        n = 12
        errors = []
        results = []

        def one(i):
            try:
                data = self._post_chat(f'ping {i}', f'user_{i % 3}')
                if data.get('error'):
                    err = data['error']
                    raise AssertionError(
                        f"{err.get('code')} {err.get('exception')}: {err.get('technical')}"
                    )
                text = (data.get('text') or data.get('response') or '').strip()
                if not text:
                    raise AssertionError(f'empty chat response: {data}')
                return text
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')
                raise

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(one, i) for i in range(n)]
            for fut in as_completed(futs):
                results.append(fut.result())

        self.assertEqual(len(results), n)
        self.assertEqual(errors, [])
        joined = ' '.join(errors).lower()
        self.assertNotIn('programmingerror', joined)
        self.assertNotIn('same thread', joined)


if __name__ == '__main__':
    unittest.main()
