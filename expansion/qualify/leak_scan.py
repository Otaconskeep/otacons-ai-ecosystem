"""Release-tree and private-Keep leak scanner.

Any unexpected hit blocks RC.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Private Keep / identity / LAN fragments that must never appear in release trees.
LEAK_PATTERNS = (
    re.compile(r'/opt/otacon'),
    re.compile(r'\bXof\b'),
    re.compile(r'\buser_primary\b'),  # product may use as relationship id — flag in release artifacts carefully
    re.compile(r'192\.168\.50\.(219|221|192|69)\b'),
    re.compile(r'\bOptiPlex\b', re.I),
    re.compile(r'\bAI9\b.*\b192\.168\b'),
    re.compile(r'(?i)(aws_secret|openai_api_key|discord_bot_token)\s*='),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'\.env\b'),
)

# Patterns allowed only in certain contexts (dev SoT / tests), blocked in RC package root
RC_BLOCKED_FILENAMES = (
    '.env',
    '.env.local',
    'signing-private.pem',
    'id_rsa',
    'bundle.key',
)

PLAINTEXT_DOSSIER_IN_RC = re.compile(r'(^|/)dossiers/[^/]+\.json$')


@dataclass
class LeakHit:
    path: str
    pattern: str
    excerpt: str = ''


@dataclass
class LeakScanReport:
    ok: bool
    hits: list = field(default_factory=list)
    scanned_files: int = 0

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'hits': [asdict(h) if hasattr(h, '__dataclass_fields__') else h for h in self.hits],
            'scanned_files': self.scanned_files,
        }


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if '__pycache__' in parts or '.git' in parts:
        return True
    if path.suffix in ('.enc', '.png', '.webp', '.jpg', '.wav', '.onnx', '.bin'):
        return True
    return False


def scan_tree(
    root: Path,
    *,
    is_release_candidate: bool = True,
    allow_user_primary: bool = False,
) -> LeakScanReport:
    root = Path(root)
    hits: list[LeakHit] = []
    scanned = 0
    patterns = list(LEAK_PATTERNS)
    if allow_user_primary:
        patterns = [p for p in patterns if 'user_primary' not in p.pattern]

    for path in root.rglob('*'):
        if not path.is_file() or _should_skip(path):
            continue
        scanned += 1
        rel = str(path.relative_to(root)).replace('\\', '/')
        name = path.name
        if name in RC_BLOCKED_FILENAMES or name.endswith('.key'):
            hits.append(LeakHit(rel, f'blocked_filename:{name}'))
            continue
        if is_release_candidate and PLAINTEXT_DOSSIER_IN_RC.search('/' + rel):
            if 'staging_src' not in path.parts and 'product_src' not in path.parts:
                hits.append(LeakHit(rel, 'plaintext_dossier_in_rc'))
                continue
        if path.suffix == '.map':
            hits.append(LeakHit(rel, 'source_map'))
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        # Cap scan size
        sample = text[:200_000]
        for pat in patterns:
            m = pat.search(sample)
            if m:
                hits.append(LeakHit(rel, pat.pattern, excerpt=m.group(0)[:80]))
    return LeakScanReport(ok=not hits, hits=hits, scanned_files=scanned)


def scan_text_blob(text: str, *, source: str = 'blob') -> list[LeakHit]:
    hits = []
    for pat in LEAK_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(LeakHit(source, pat.pattern, excerpt=m.group(0)[:80]))
    return hits
