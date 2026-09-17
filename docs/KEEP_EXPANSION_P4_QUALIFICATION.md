# Keep Expansion — P4 Qualification

**Status:** P4 release qualification / failure recovery  
**Baseline:** `c298012` P3 protected release (must remain intact)  
**Version:** `0.4.0-rc1`

## Objective

Prove Expansion can be installed, upgraded, interrupted, restarted, repaired,
rolled back, reinstalled, and run offline/degraded **without losing user data
or damaging Core**.

## Acceptance command

```bash
python3 scripts/otacon_qualify_expansion.py
python3 scripts/otacon_qualify_expansion.py --channel protected --package /path/to/rc
```

## RC build

```bash
python3 scripts/build_expansion_rc.py --out /tmp/otacon-rc
```

Artifact folder: `keep-expansion-0.4.0-rc1/`

## Test matrix (automated)

| Area | Module / test |
|---|---|
| Brutal state survival | `tests/test_expansion_p4_qualification.py::TestBrutalStateSurvival` |
| Failure injection | `TestFailureInjectionPhases` |
| Tamper / keys | `TestTamperAndKeys` |
| Disk / offline / repair / backup | `TestDiskOfflineRepairBackup` |
| Concurrency | `TestConcurrencyLeakLoggingHealth::test_concurrency_stress` |
| Leak scan / redaction / health | same class |
| Acceptance + Windows classification | `TestAcceptanceAndWindows` |
| Startup recovery | `TestStartupRecovery` |
| Migration idempotence | `TestMigrationIdempotence` |

## Windows E2E classification

Host for this qualification run: Linux (PVE), not a Windows CI runner.

| Layer | Result |
|---|---|
| Static installer contracts (`OtaconsKeep-Setup.bat`, assistant) | **PASS** |
| Live Windows/DPAPI/reboot/elevation matrix | **ENVIRONMENT_UNSUPPORTED** / **TEST_INFRA_FAILURE** |

Live Windows failures on this host are **not** product failures.

## Persistence note

P4 concurrency stress exposed JobStore RMW races; fixed via `persist.update_json`
(single flock load-modify-save). Measured: 4 workers × 8 iterations passed.
SQLite migration deferred while JSON+flock remains adequate under this load.

## Unresolved YELLOW

- Linux local keys: permissions `0600` (not OS keyring/TPM) — see SECURITY.md
- Live Windows E2E matrix awaits Windows runner
- Full multi-GPU / low-RAM hardware matrix not exercised on this host
