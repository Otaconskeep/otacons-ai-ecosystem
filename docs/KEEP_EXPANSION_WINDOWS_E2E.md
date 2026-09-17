# Keep Expansion — Windows E2E

## Classification rule

Do **not** classify infrastructure failure as product failure.

| Code | Meaning |
|---|---|
| `PASS` | Static and/or live checks succeeded |
| `PRODUCT_FAILURE` | Installer/source contract broken |
| `TEST_INFRA_FAILURE` | Runner/tooling could not execute live matrix |
| `ENVIRONMENT_UNSUPPORTED` | Host is not Windows (e.g. Linux PVE CI) |

## What is covered on every host

Static contracts via `expansion.qualify.windows_e2e.run_windows_static_contracts`
and `tests/test_windows_installer_release_gate.py`:

- `OtaconsKeep-Setup.bat` encoding/UTF-8 guards
- Windows setup assistant Repair/Force/WSL/port 5757 paths
- Honest exit codes / phase markers

## What requires a Windows runner

- Fresh user profile
- Paths with spaces / Unicode username
- Non-admin vs elevated install
- Reboot/resume
- WSL present/absent, Docker present/absent
- Port conflicts
- DPAPI key survives restart
- DPAPI key not trivially portable to unrelated machine
- Expansion health after reboot

## This qualification host

Linux `pve` — live matrix: **ENVIRONMENT_UNSUPPORTED** with static **PASS**.
