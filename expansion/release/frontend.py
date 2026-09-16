"""Frontend hardening for protected Expansion builds.

Production: minify/bundle-ish strip, no source maps, no embedded secrets,
no dev-only debug routes that expose prompts/internal state.
Developer builds retain diagnostics.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

_SOURCE_MAP_RE = re.compile(r'^//# sourceMappingURL=.*$', re.M)
_SECRET_PATTERNS = (
    re.compile(r'api[_-]?key\s*[:=]\s*[\'"][^\'"]+[\'"]', re.I),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY'),
)


def strip_source_maps(text: str) -> str:
    return _SOURCE_MAP_RE.sub('', text)


def rough_minify_js(text: str) -> str:
    """Conservative minify: drop source maps + collapse trivial blank lines.

    Not a full bundler — enough to strip maps/debug breadcrumbs for release.
    """
    text = strip_source_maps(text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('//') and 'sourceMappingURL' in stripped:
            continue
        lines.append(line)
    # Collapse runs of empty lines
    out = []
    blank = 0
    for line in lines:
        if not line.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(line)
    return '\n'.join(out) + '\n'


def scan_for_embedded_secrets(text: str) -> list:
    hits = []
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def harden_frontend_tree(src: Path, dest: Path) -> dict:
    """Copy UI tree into dest with release hardening applied to JS/CSS."""
    src = Path(src)
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    report = {'files': 0, 'stripped_maps': 0, 'secret_hits': []}
    for path in src.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix == '.map':
            report['stripped_maps'] += 1
            continue  # omit source maps entirely
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in ('.js', '.mjs', '.css', '.html'):
            text = path.read_text(encoding='utf-8', errors='replace')
            secrets = scan_for_embedded_secrets(text)
            if secrets:
                report['secret_hits'].extend(secrets)
            if path.suffix in ('.js', '.mjs'):
                if 'sourceMappingURL' in text:
                    report['stripped_maps'] += 1
                text = rough_minify_js(text)
            # Strip common dev-only debug query hooks from HTML
            if path.suffix == '.html':
                text = text.replace('?debug=1', '').replace('debug=1&', '')
            target.write_text(text, encoding='utf-8')
        else:
            shutil.copy2(path, target)
        report['files'] += 1
    if report['secret_hits']:
        raise ValueError(f'embedded secrets detected in frontend: {report["secret_hits"][:3]}')
    return report
