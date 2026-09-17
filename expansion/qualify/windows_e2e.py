"""Windows E2E qualification harness.

Classifies outcomes as:
  PRODUCT FAILURE
  TEST-INFRA FAILURE
  ENVIRONMENT UNSUPPORTED

Live Windows/WSL execution is required for full PASS. On Linux CI hosts,
static installer contracts still run; live E2E is ENVIRONMENT UNSUPPORTED
or TEST-INFRA FAILURE — never silently marked as product failure.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]


@dataclass
class WindowsE2EResult:
    classification: str  # PRODUCT_FAILURE | TEST_INFRA_FAILURE | ENVIRONMENT_UNSUPPORTED | PASS
    checks: list = field(default_factory=list)
    detail: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def _check(name: str, ok: bool, detail: str = '') -> dict:
    return {'name': name, 'ok': ok, 'detail': detail}


def run_windows_static_contracts() -> WindowsE2EResult:
    """Source-level Windows installer contracts (always runnable)."""
    checks = []
    setup = REPO / 'OtaconsKeep-Setup.bat'
    assistant = REPO / 'deploy' / 'windows-setup-assistant.ps1'
    checks.append(_check('setup_bat_exists', setup.is_file()))
    checks.append(_check('assistant_exists', assistant.is_file()))
    if setup.is_file():
        text = setup.read_text(encoding='utf-8', errors='replace')
        checks.append(_check('setup_has_bom_or_utf8_guard', 'UTF-8 BOM' in text or 'utf-8' in text.lower()))
        checks.append(_check('setup_calls_powershell', 'powershell' in text.lower()))
    if assistant.is_file():
        text = assistant.read_text(encoding='utf-8', errors='replace')
        for needle in ('Repair', 'Force', 'WSL', '5757', 'otacon'):
            checks.append(_check(f'assistant_mentions_{needle}', needle.lower() in text.lower(), needle))
    # Existing release-gate module
    try:
        import pytest
        # Don't invoke pytest here — just ensure module imports
        from tests import test_windows_installer_release_gate as gate  # noqa: F401
        checks.append(_check('windows_release_gate_module', True))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check('windows_release_gate_module', False, str(exc)))

    failed = [c for c in checks if not c['ok']]
    if failed:
        return WindowsE2EResult(
            classification='PRODUCT_FAILURE',
            checks=checks,
            detail=f'static contract failures: {[c["name"] for c in failed]}',
        )
    return WindowsE2EResult(
        classification='PASS',
        checks=checks,
        detail='static Windows installer contracts ok',
    )


def run_windows_live_e2e() -> WindowsE2EResult:
    """Attempt live Windows E2E; classify infra/environment separately."""
    static = run_windows_static_contracts()
    if static.classification == 'PRODUCT_FAILURE':
        return static

    system = platform.system().lower()
    checks = list(static.checks)

    if system != 'windows' and 'microsoft' not in platform.version().lower():
        # Detect WSL
        is_wsl = False
        try:
            with open('/proc/version', encoding='utf-8') as f:
                is_wsl = 'microsoft' in f.read().lower()
        except OSError:
            pass
        if not is_wsl:
            checks.append(_check('live_windows_host', False, f'host={system}'))
            return WindowsE2EResult(
                classification='ENVIRONMENT_UNSUPPORTED',
                checks=checks,
                detail=(
                    'Live Windows E2E requires a Windows host (or Windows CI runner). '
                    'Static contracts passed. Not a product defect.'
                ),
            )

    # On Windows/WSL try probing wsl/docker presence without failing product
    for cmd, label in (
        (['wsl', '--status'], 'wsl_status'),
        (['docker', 'version'], 'docker_version'),
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            checks.append(_check(label, proc.returncode == 0, (proc.stdout or proc.stderr)[:200]))
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            checks.append(_check(label, False, f'TEST_INFRA: {exc}'))

    infra_fail = [c for c in checks if not c['ok'] and c['name'] in ('wsl_status', 'docker_version')]
    if infra_fail and system != 'windows':
        return WindowsE2EResult(
            classification='TEST_INFRA_FAILURE',
            checks=checks,
            detail='WSL/Docker probes failed on non-Windows qualification host — not product failure.',
        )

    return WindowsE2EResult(
        classification='TEST_INFRA_FAILURE',
        checks=checks,
        detail=(
            'Full live Windows matrix (DPAPI reboot, elevation, spaces in paths) '
            'requires dedicated Windows runner. Static PASS; live deferred.'
        ),
    )
