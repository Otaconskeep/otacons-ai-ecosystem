"""Thread-safe SQLite memory store.

Architecture (required):
  - No shared Connection/Cursor across HTTP worker threads
  - Fresh sqlite3.connect() per operation
  - Scoped connections that always close (sqlite3's `with conn` only
    commits/rolls back — it does NOT close; we close explicitly)
  - WAL + busy_timeout for concurrent readers/writers
  - Do not "fix" threading by disabling SQLite's same-thread check;
    prefer per-request/per-operation connections instead
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS agents(id TEXT, user_id TEXT, PRIMARY KEY(id,user_id));
CREATE TABLE IF NOT EXISTS conversations(
  id TEXT PRIMARY KEY, user_id TEXT, agent_id TEXT, title TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT, user_id TEXT, agent_id TEXT,
  role TEXT, content TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT, agent_id TEXT, content TEXT,
  source_conversation_id TEXT,
  memory_type TEXT DEFAULT 'fact',
  active INTEGER DEFAULT 1,
  created_at REAL, updated_at REAL
);
"""


class MemoryStore:
    """SQLite-backed conversation + memory store (one connection per operation)."""

    def __init__(self, path, *, timeout: float = 30.0):
        self.db_path = Path(path)
        self.path = self.db_path  # backward-compatible alias
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = float(timeout)
        self._init_lock = threading.Lock()
        # Intentionally no self.db / self.conn — those caused cross-thread crashes.
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=%d' % int(self.timeout * 1000))
        try:
            conn.execute('PRAGMA journal_mode=WAL')
        except sqlite3.Error:
            pass
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Fresh connection; always closes. Prefer this over bare `_connect()`."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._init_lock:
            with self.connection() as conn:
                conn.executescript(_SCHEMA)

    def migrate(self) -> None:
        self._ensure_schema()

    def ping(self) -> bool:
        """Cheap readiness probe used by /api/capabilities (CHAT READY)."""
        with self.connection() as conn:
            conn.execute('SELECT 1').fetchone()
        return True

    def create_conversation(self, user, agent, title='New conversation'):
        cid = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                'INSERT INTO conversations VALUES(?,?,?,?,?)',
                (cid, user, agent, title, time.time()),
            )
        return cid

    def append(self, cid, user, agent, role, content):
        with self.connection() as conn:
            conn.execute(
                'INSERT INTO messages(conversation_id,user_id,agent_id,role,content,created_at) '
                'VALUES(?,?,?,?,?,?)',
                (cid, user, agent, role, content, time.time()),
            )

    def list_conversations(self, user, agent):
        with self.connection() as conn:
            rows = conn.execute(
                'SELECT * FROM conversations WHERE user_id=? AND agent_id=? ORDER BY created_at DESC',
                (user, agent),
            ).fetchall()
            return [dict(x) for x in rows]

    def get_conversation(self, cid, user, agent):
        with self.connection() as conn:
            row = conn.execute(
                'SELECT * FROM conversations WHERE id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            ).fetchone()
            msgs = conn.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (cid, 20),
            ).fetchall()
            messages = [dict(x) for x in msgs][::-1]
            return {
                'conversation': dict(row) if row else None,
                'messages': messages,
            }

    def delete_conversation(self, cid, user, agent):
        with self.connection() as conn:
            conn.execute(
                'DELETE FROM messages WHERE conversation_id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            )
            conn.execute(
                'DELETE FROM conversations WHERE id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            )

    def messages(self, cid, limit=20):
        with self.connection() as conn:
            rows = conn.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (cid, limit),
            ).fetchall()
            return [dict(x) for x in rows][::-1]

    def remember(self, user, agent, content, source=None):
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                'INSERT INTO memories(user_id,agent_id,content,source_conversation_id,created_at,updated_at) '
                'VALUES(?,?,?,?,?,?)',
                (user, agent, content, source, now, now),
            )

    def retrieve(self, user, agent, query, limit=5):
        terms = set(query.lower().split())
        with self.connection() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE user_id=? AND agent_id=? AND active=1',
                (user, agent),
            ).fetchall()
            ranked = sorted(
                rows,
                key=lambda r: sum(t in r['content'].lower() for t in terms),
                reverse=True,
            )
            return [
                dict(x) for x in ranked[:limit]
                if any(t in x['content'].lower() for t in terms)
            ]

    def list_memories(self, user, agent):
        with self.connection() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE user_id=? AND agent_id=? AND active=1 ORDER BY id',
                (user, agent),
            ).fetchall()
            return [dict(x) for x in rows]

    def delete_memory(self, mid, user, agent):
        with self.connection() as conn:
            conn.execute(
                'UPDATE memories SET active=0,updated_at=? WHERE id=? AND user_id=? AND agent_id=?',
                (time.time(), mid, user, agent),
            )

    def close(self) -> None:
        """No persistent connection; API compatibility only."""
        return
