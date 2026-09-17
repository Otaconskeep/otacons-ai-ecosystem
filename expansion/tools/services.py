"""Service inspect / restart — systemctl allowlist."""
from __future__ import annotations

import re
import shlex
import subprocess

_UNIT_RE = re.compile(r'^[a-zA-Z0-9@_.\\-]+$')


def service_op(capability: str, kwargs: dict) -> tuple[dict, str]:
    unit = (kwargs.get('unit') or kwargs.get('service') or kwargs.get('name') or '').strip()
    if capability == 'services.inspect':
        if unit:
            if not _UNIT_RE.match(unit):
                raise ValueError('invalid unit')
            cmd = f'systemctl is-active {shlex.quote(unit)}'
        else:
            cmd = 'systemctl status'
        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
        return {
            'command': cmd,
            'exit_code': proc.returncode,
            'stdout': (proc.stdout or '')[-4000:],
            'stderr': (proc.stderr or '')[-1000:],
        }, f'services.inspect → {proc.returncode}'

    if capability == 'services.restart':
        if not unit or not _UNIT_RE.match(unit):
            raise ValueError('unit required')
        cmd = f'systemctl restart {shlex.quote(unit)}'
        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=60)
        return {
            'command': cmd,
            'exit_code': proc.returncode,
            'stdout': (proc.stdout or '')[-2000:],
            'stderr': (proc.stderr or '')[-1000:],
        }, f'services.restart {unit} → {proc.returncode}'
    raise ValueError(capability)
