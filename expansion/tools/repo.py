"""Repo / files tools — confined to workspace root."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout

SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.cursor', '.tox',
}


def workspace_root(layout: Optional[StateLayout] = None, root: Optional[str] = None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    env = os.environ.get('OTACON_WORKSPACE') or os.environ.get('OTACON_REPO_ROOT')
    if env:
        return Path(env).expanduser().resolve()
    layout = layout or resolve_layout()
    # product_root is .../expansion → repo is parent
    return layout.product_root.resolve().parent


def _safe_path(rel: str, *, root: Path) -> Path:
    rel = (rel or '').lstrip('/')
    if not rel or '..' in Path(rel).parts:
        raise ValueError('invalid path')
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError('path escapes workspace') from exc
    return target


def repo_read(path: str, *, root: Optional[str] = None, layout: Optional[StateLayout] = None) -> tuple[dict, str]:
    ws = workspace_root(layout, root)
    target = _safe_path(path, root=ws)
    if not target.is_file():
        raise FileNotFoundError(path)
    if target.stat().st_size > 2_000_000:
        raise ValueError('file too large')
    text = target.read_text(encoding='utf-8', errors='replace')
    return {
        'path': str(target.relative_to(ws)),
        'bytes': len(text.encode('utf-8')),
        'content': text[:100_000],
    }, f'read {path}'


def repo_write(path: str, content: str, *, root: Optional[str] = None, layout: Optional[StateLayout] = None) -> tuple[dict, str]:
    ws = workspace_root(layout, root)
    target = _safe_path(path, root=ws)
    # Refuse writes into secrets / .env
    name = target.name.lower()
    if name in ('.env', 'credentials.json', 'lan_token') or name.endswith('.pem'):
        raise PermissionError('refusing to write secret-like path')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content if isinstance(content, str) else str(content), encoding='utf-8')
    return {'path': str(target.relative_to(ws)), 'bytes': len(content or '')}, f'write {path}'


def repo_search(query: str, *, root: Optional[str] = None, layout: Optional[StateLayout] = None) -> tuple[dict, str]:
    q = (query or '').strip()
    if not q:
        raise ValueError('query required')
    ws = workspace_root(layout, root)
    hits = []
    pattern = re.compile(re.escape(q), re.I)
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in filenames:
            if len(hits) >= 25:
                break
            if not any(fn.endswith(ext) for ext in (
                '.py', '.js', '.ts', '.tsx', '.md', '.json', '.yml', '.yaml', '.toml', '.css', '.html',
            )):
                continue
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > 500_000:
                    continue
                text = fp.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append({
                        'path': str(fp.relative_to(ws)),
                        'line': i,
                        'text': line.strip()[:200],
                    })
                    if len(hits) >= 25:
                        break
        if len(hits) >= 25:
            break
    return {'query': q, 'hits': hits, 'root': str(ws)}, f'repo.search({q!r}) → {len(hits)}'
