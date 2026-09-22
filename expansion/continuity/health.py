# -*- coding: utf-8 -*-
"""Structured health / failure reporting for Premium continuity + Hermes.

Core layers must never silently swallow exceptions on the chat path.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Optional

_log = logging.getLogger('expansion.continuity.health')
_lock = threading.Lock()
_recent: deque = deque(maxlen=200)
_layer_status: dict[str, dict] = {}

LAYERS = (
    'hermes',
    'state_engine',
    'relationship_engine',
    'memory_engine',
    'affect_engine',
    'persistence',
    'context_assembly',
    'final_render',
    'preferences',
)


def record_ok(layer: str, *, detail: str = '') -> None:
    layer = (layer or 'unknown').strip()
    with _lock:
        prev = _layer_status.get(layer) or {}
        # Do not erase a failure recorded in the last 2s (failure-injection visibility)
        if prev.get('ok') is False and (time.time() - float(prev.get('ts') or 0)) < 2.0:
            return
        _layer_status[layer] = {
            'ok': True,
            'detail': detail,
            'ts': time.time(),
            'error': None,
        }


def record_failure(
    layer: str,
    exc: BaseException | str,
    *,
    detail: str = '',
    reraise: bool = False,
) -> dict:
    layer = (layer or 'unknown').strip()
    err = str(exc)
    entry = {
        'ok': False,
        'layer': layer,
        'error': err,
        'detail': detail,
        'ts': time.time(),
    }
    with _lock:
        _layer_status[layer] = entry
        _recent.appendleft(entry)
    _log.error('continuity_layer_failure layer=%s detail=%s error=%s', layer, detail, err)
    if reraise and isinstance(exc, BaseException):
        raise exc
    return entry


def snapshot() -> dict:
    with _lock:
        return {
            'layers': {k: dict(v) for k, v in _layer_status.items()},
            'recent_failures': list(_recent)[:20],
            'healthy': all(
                (_layer_status.get(L) or {}).get('ok', True) for L in LAYERS
                if L in _layer_status
            ),
        }


def clear() -> None:
    with _lock:
        _layer_status.clear()
        _recent.clear()


class LayerGuard:
    """Context manager that records ok/failure for a named layer."""

    def __init__(self, layer: str, *, detail: str = '', soft: bool = True):
        self.layer = layer
        self.detail = detail
        self.soft = soft
        self.error: Optional[dict] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            record_ok(self.layer, detail=self.detail)
            return False
        self.error = record_failure(self.layer, exc, detail=self.detail)
        # soft=True swallows after recording (caller continues with degraded path)
        return bool(self.soft)
