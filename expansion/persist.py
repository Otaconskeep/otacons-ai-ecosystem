"""Atomic JSON / JSONL persistence helpers for Expansion user state.

P1 introduced many JSON writers. P2 hardens them with:
- write-temp-then-rename (atomic replace on same filesystem)
- optional flock around multi-step updates
- documented concurrency limits

Limitations (documented, not silent):
- Concurrent writers to the *same* file serialize via flock when used.
- Cross-process readers may see a torn JSONL append without flock; prefer
  append_jsonl() which locks.
- Not a full ACID database; if Expansion grows many competing writers for
  the same high-churn store, migrate that store to SQLite via migrations.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional


@contextmanager
def file_lock(path: Path, *, shared: bool = False) -> Iterator[None]:
    """Advisory flock around a lock sidecar next to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + '.lock')
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> Path:
    """Atomically replace `path` with JSON content."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp',
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, default=str)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    return path


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    with file_lock(path, shared=True):
        return json.loads(path.read_text(encoding='utf-8'))


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str) + '\n'
    with file_lock(path):
        with path.open('a', encoding='utf-8') as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


def read_jsonl(path: Path, *, limit: Optional[int] = None) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    with file_lock(path, shared=True):
        lines = path.read_text(encoding='utf-8').splitlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    out = []
    for line in lines:
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out
