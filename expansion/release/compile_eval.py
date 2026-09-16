"""Compile/obfuscation evaluation for sensitive Expansion modules (P3F).

Evaluate — do not blindly apply. Prefer maintainability and testability.
Candidates if/when release engineering opts in:

  - Nuitka / Cython / native extensions for:
      agent runtime, emotion/relationship calculations,
      protected resource loader, premium orchestration,
      entitlement-sensitive code
  - Frontend minify (always for protected builds — see frontend.py)

This module records policy + a dry-run inventory; it does not compile.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


PRIORITY_MODULES = (
    'expansion/runtime.py',
    'expansion/emotion.py',
    'expansion/relationship_graph.py',
    'expansion/protected/loader.py',
    'expansion/protected/bundle.py',
    'expansion/entitlement.py',
    'expansion/pipeline.py',
)


@dataclass
class CompileEvalReport:
    policy: str
    candidates: list = field(default_factory=list)
    deferred: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_compile_candidates(repo_root: Path) -> CompileEvalReport:
    repo_root = Path(repo_root)
    present = []
    missing = []
    for rel in PRIORITY_MODULES:
        path = repo_root / rel
        if path.is_file():
            present.append({
                'path': rel,
                'bytes': path.stat().st_size,
                'recommendation': 'candidate for Nuitka/Cython in protected CI only',
            })
        else:
            missing.append(rel)
    return CompileEvalReport(
        policy=(
            'Do not blindly compile. Keep unit tests on Python sources. '
            'Protected CI may emit native extensions for priority modules only.'
        ),
        candidates=present,
        deferred=missing,
        notes=[
            'No aggressive anti-debug/anti-reverse tricks.',
            'Strip source maps and debug metadata in frontend release builds.',
            'Maintainability and testability outrank obfuscation depth.',
        ],
    )
