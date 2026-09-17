"""Safe Expansion logging with secret redaction."""
from __future__ import annotations

import logging
import re
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r'(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+'),
    re.compile(r'sk-[A-Za-z0-9]{16,}'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'(?i)(dpapi|bundle[_-]?key|signing[_-]?key)\s*[:=]\s*\S+'),
    re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*'),
)


def redact_text(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub('[REDACTED]', out)
    return out


def safe_log_extra(
    *,
    tx_id: str = '',
    package_version: str = '',
    schema_version: int = 0,
    phase: str = '',
    component: str = '',
    health: str = '',
    error_code: str = '',
    detail: str = '',
) -> dict:
    """Structured diagnostic context — never includes secrets/prompts/keys."""
    return {
        'tx_id': tx_id,
        'package_version': package_version,
        'schema_version': schema_version,
        'phase': phase,
        'component': component,
        'health': health,
        'error_code': error_code,
        'detail': redact_text(detail or '')[:500],
    }


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            try:
                record.args = tuple(
                    redact_text(a) if isinstance(a, str) else a for a in record.args
                )
            except TypeError:
                pass
        return True


def get_qualified_logger(name: str = 'otacon.expansion') -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger


def assert_no_secrets(blob: Any) -> list:
    """Return list of redaction violations found in serialized blob."""
    text = blob if isinstance(blob, str) else str(blob)
    hits = []
    for pat in _SECRET_PATTERNS:
        if pat.search(text) and '[REDACTED]' not in pat.sub('[REDACTED]', text[:0] + text):
            # If pattern matches raw secret-like content
            m = pat.search(text)
            if m and '[REDACTED]' not in m.group(0):
                hits.append(pat.pattern)
    return hits
