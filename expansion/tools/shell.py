"""Allowlisted shell / git / tests / logs — policy still required upstream."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from expansion.tools.repo import workspace_root
from expansion.state_layout import StateLayout

# Explicit allowlist prefixes — no free-form shell.
_ALLOW = (
    'git status', 'git diff', 'git log', 'git branch', 'git rev-parse',
    'git show', 'ls', 'pwd', 'head', 'tail', 'wc', 'uname', 'df',
    'python3 -m pytest', 'python3 -m compileall',
    'docker ps', 'docker version', 'docker inspect', 'docker logs',
    'systemctl is-active', 'systemctl status', 'systemctl show',
)

_DENY = re.compile(
    r'(rm\s+-rf|mkfs|dd\s+if=|>\s*/dev/|curl\s+[^\n]*\|\s*(sh|bash)|'
    r'wget\s+[^\n]*\|\s*(sh|bash)|chmod\s+-R\s+777|shutdown|reboot|'
    r'userdel|passwd|chown\s+-R\s+|/etc/shadow)',
    re.I,
)


def _allowed(command: str) -> bool:
    cmd = ' '.join(shlex.split(command or ''))
    if not cmd or _DENY.search(cmd):
        return False
    return any(cmd == a or cmd.startswith(a + ' ') for a in _ALLOW)


def shell_execute(command: str) -> tuple[dict, str]:
    cmd = (command or '').strip()
    if not _allowed(cmd):
        raise PermissionError(f'shell command not on allowlist: {cmd[:120]}')
    proc = subprocess.run(
        shlex.split(cmd),
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(workspace_root()),
    )
    out = (proc.stdout or '')[-8000:]
    err = (proc.stderr or '')[-4000:]
    return {
        'command': cmd,
        'exit_code': proc.returncode,
        'stdout': out,
        'stderr': err,
    }, f'shell `{cmd}` → exit {proc.returncode}'


def run_tests(args: str = '', *, layout: Optional[StateLayout] = None) -> tuple[dict, str]:
    ws = workspace_root(layout)
    # Prefer expansion-focused suite when present
    target = 'tests/test_expansion_rex.py'
    if not (ws / target).exists():
        target = 'tests'
    extra = shlex.split(args) if args else ['-q', '--tb=line']
    cmd = ['python3', '-m', 'pytest', target, *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(ws))
    return {
        'command': ' '.join(cmd),
        'exit_code': proc.returncode,
        'stdout': (proc.stdout or '')[-6000:],
        'stderr': (proc.stderr or '')[-2000:],
        'passed': proc.returncode == 0,
    }, f'tests.run → exit {proc.returncode}'


def git_op(capability: str, kwargs: dict) -> tuple[dict, str]:
    if capability == 'git.branch':
        name = (kwargs.get('name') or kwargs.get('branch') or '').strip()
        if not name or not re.match(r'^[a-zA-Z0-9._/-]+$', name):
            raise ValueError('invalid branch name')
        # create/switch only via allowlisted git — use checkout -b through shell_execute path
        return shell_execute(f'git branch {name}')
    if capability == 'git.commit':
        # Commit requires staged changes; we only allow message inspection path —
        # actual commit is high-impact: use `git status` evidence instead unless msg provided
        msg = (kwargs.get('message') or '').strip()
        if not msg:
            return shell_execute('git status')
        # Still refuse arbitrary commit in default autonomy — record intent
        st = shell_execute('git status')
        st[0]['commit_intent'] = msg
        st[0]['committed'] = False
        st[0]['note'] = 'git.commit records intent; auto-commit disabled until owner enables'
        return st[0], 'git.commit intent recorded (auto-commit off)'
    raise ValueError(capability)


def read_logs(path_or_unit: str) -> tuple[dict, str]:
    target = (path_or_unit or '').strip()
    if not target:
        raise ValueError('path or unit required')
    if '/' in target or target.endswith('.log'):
        p = Path(target)
        if not p.is_file():
            raise FileNotFoundError(target)
        text = p.read_text(encoding='utf-8', errors='replace')[-8000:]
        return {'path': target, 'tail': text}, f'logs.read {target}'
    if not target.replace('-', '').replace('_', '').replace('.', '').isalnum():
        raise ValueError('invalid unit')
    return shell_execute(f'systemctl status {target}')
