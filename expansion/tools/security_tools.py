"""Sentry-facing security scan helpers (policy-gated)."""
from __future__ import annotations

from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.tools.repo import repo_search, workspace_root


def security_scan(*, layout: Optional[StateLayout] = None, **kwargs) -> tuple[dict, str]:
    layout = layout or resolve_layout()
    findings = []
    # Heuristic leak patterns in workspace (not a full vuln scanner)
    for needle in ('API_KEY=', 'SECRET=', 'password=', 'BEGIN RSA PRIVATE KEY'):
        try:
            data, _ = repo_search(needle, layout=layout)
            for hit in data.get('hits') or []:
                findings.append({
                    'severity': 'high' if 'PRIVATE' in needle else 'medium',
                    'pattern': needle,
                    'path': hit.get('path'),
                    'line': hit.get('line'),
                })
        except Exception:
            continue
    return {
        'findings': findings[:40],
        'workspace': str(workspace_root(layout)),
        'ok': len(findings) == 0,
    }, f'security.scan → {len(findings)} findings'
