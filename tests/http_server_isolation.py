"""Helpers so HTTP tests do not leak installer.server bind/auth globals.

LAN-auth tests flip ``BIND_MODE`` / ``LAN_TOKEN`` on the shared module.
Without reset, later ThreadingHTTPServer suites (memory concurrency, etc.)
see fake 401s / timeouts during installer self-check — the live app is fine.
"""
from __future__ import annotations

from typing import Any


def snapshot_server_bind(server_mod) -> dict[str, Any]:
    return {
        'BIND_HOST': getattr(server_mod, 'BIND_HOST', '127.0.0.1'),
        'BIND_MODE': getattr(server_mod, 'BIND_MODE', 'local'),
        'LAN_TOKEN': getattr(server_mod, 'LAN_TOKEN', None),
    }


def restore_server_bind(server_mod, snap: dict[str, Any]) -> None:
    server_mod.BIND_HOST = snap.get('BIND_HOST', '127.0.0.1')
    server_mod.BIND_MODE = snap.get('BIND_MODE', 'local')
    server_mod.LAN_TOKEN = snap.get('LAN_TOKEN', None)


def force_local_bind(server_mod) -> dict[str, Any]:
    """Force local (no bearer) mode; return prior snapshot for restore."""
    snap = snapshot_server_bind(server_mod)
    server_mod.BIND_HOST = '127.0.0.1'
    server_mod.BIND_MODE = 'local'
    server_mod.LAN_TOKEN = None
    return snap


def snapshot_security_paths(sec_mod) -> dict[str, Any]:
    return {
        'CONFIG_ROOT': getattr(sec_mod, 'CONFIG_ROOT', None),
        'TOKEN_PATH': getattr(sec_mod, 'TOKEN_PATH', None),
    }


def restore_security_paths(sec_mod, snap: dict[str, Any]) -> None:
    if snap.get('CONFIG_ROOT') is not None:
        sec_mod.CONFIG_ROOT = snap['CONFIG_ROOT']
    if snap.get('TOKEN_PATH') is not None:
        sec_mod.TOKEN_PATH = snap['TOKEN_PATH']
