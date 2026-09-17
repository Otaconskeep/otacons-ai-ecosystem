"""Docker tools — inspect-first; manage is tightly allowlisted."""
from __future__ import annotations

import shlex
import subprocess


def docker_op(capability: str, kwargs: dict) -> tuple[dict, str]:
    if capability == 'docker.inspect':
        target = (kwargs.get('container') or kwargs.get('name') or kwargs.get('id') or '').strip()
        if target:
            cmd = f'docker inspect {shlex.quote(target)}'
        else:
            cmd = 'docker ps'
        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
        return {
            'command': cmd,
            'exit_code': proc.returncode,
            'stdout': (proc.stdout or '')[-8000:],
            'stderr': (proc.stderr or '')[-2000:],
        }, f'docker.inspect → {proc.returncode}'

    # docker.manage — only restart of named container, never prune/rm -f volume
    action = (kwargs.get('action') or 'ps').strip()
    name = (kwargs.get('container') or kwargs.get('name') or '').strip()
    if action == 'ps':
        cmd = 'docker ps -a'
    elif action == 'restart' and name and name.replace('-', '').replace('_', '').isalnum():
        cmd = f'docker restart {shlex.quote(name)}'
    else:
        raise PermissionError(f'docker.manage action not allowed: {action!r}')
    proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=60)
    return {
        'command': cmd,
        'exit_code': proc.returncode,
        'stdout': (proc.stdout or '')[-4000:],
        'stderr': (proc.stderr or '')[-2000:],
    }, f'docker.manage {action} → {proc.returncode}'
