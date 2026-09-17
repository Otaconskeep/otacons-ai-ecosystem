"""Thread-safe SQLite memory store.

Each public method opens its own connection, commits/rolls back, and closes.
No connection is shared across HTTP worker threads.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

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
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = float(timeout)
        self._init_lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        # Fresh connection per call — never reuse across threads.
        # Do NOT use check_same_thread=False.
        db = sqlite3.connect(
            str(self.path),
            timeout=self.timeout,
            isolation_level='DEFERRED',
        )
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout = %d' % int(self.timeout * 1000))
        try:
            db.execute('PRAGMA journal_mode=WAL')
        except sqlite3.Error:
            pass
        return db

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
            db.commit()
        except Exception:
            try:
                db.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            db.close()

    def _ensure_schema(self) -> None:
        with self._init_lock:
            with self.connection() as db:
                db.executescript(_SCHEMA)

    def migrate(self) -> None:
        """Idempotent schema ensure (public for older callers/tests)."""
        self._ensure_schema()

    def create_conversation(self, user, agent, title='New conversation'):
        cid = str(uuid.uuid4())
        with self.connection() as db:
            db.execute(
                'INSERT INTO conversations VALUES(?,?,?,?,?)',
                (cid, user, agent, title, time.time()),
            )
        return cid

    def append(self, cid, user, agent, role, content):
        with self.connection() as db:
            db.execute(
                'INSERT INTO messages(conversation_id,user_id,agent_id,role,content,created_at) '
                'VALUES(?,?,?,?,?,?)',
                (cid, user, agent, role, content, time.time()),
            )

    def list_conversations(self, user, agent):
        with self.connection() as db:
            rows = db.execute(
                'SELECT * FROM conversations WHERE user_id=? AND agent_id=? ORDER BY created_at DESC',
                (user, agent),
            ).fetchall()
            return [dict(x) for x in rows]

    def get_conversation(self, cid, user, agent):
        with self.connection() as db:
            row = db.execute(
                'SELECT * FROM conversations WHERE id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            ).fetchone()
            msgs = db.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (cid, 20),
            ).fetchall()
            messages = [dict(x) for x in msgs][::-1]
            return {
                'conversation': dict(row) if row else None,
                'messages': messages,
            }

    def delete_conversation(self, cid, user, agent):
        with self.connection() as db:
            db.execute(
                'DELETE FROM messages WHERE conversation_id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            )
            db.execute(
                'DELETE FROM conversations WHERE id=? AND user_id=? AND agent_id=?',
                (cid, user, agent),
            )

    def messages(self, cid, limit=20):
        with self.connection() as db:
            rows = db.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (cid, limit),
            ).fetchall()
            return [dict(x) for x in rows][::-1]

    def remember(self, user, agent, content, source=None):
        now = time.time()
        with self.connection() as db:
            db.execute(
                'INSERT INTO memories(user_id,agent_id,content,source_conversation_id,created_at,updated_at) '
                'VALUES(?,?,?,?,?,?)',
                (user, agent, content, source, now, now),
            )

    def retrieve(self, user, agent, query, limit=5):
        terms = set(query.lower().split())
        with self.connection() as db:
            rows = db.execute(
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
        with self.connection() as db:
            rows = db.execute(
                'SELECT * FROM memories WHERE user_id=? AND agent_id=? AND active=1 ORDER BY id',
                (user, agent),
            ).fetchall()
            return [dict(x) for x in rows]

    def delete_memory(self, mid, user, agent):
        with self.connection() as db:
            db.execute(
                'UPDATE memories SET active=0,updated_at=? WHERE id=? AND user_id=? AND agent_id=?',
                (time.time(), mid, user, agent),
            )

    def close(self) -> None:
        """No persistent connection to close; kept for API compatibility."""
        return
