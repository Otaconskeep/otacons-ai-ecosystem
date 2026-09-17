# Keep Expansion — RC Checklist

**Candidate:** `keep-expansion-0.4.0-rc1`  
**Source commit:** (fill at promote time)  
**P3 baseline intact:** `c298012`

## Build

- [ ] Clean checkout
- [ ] `python3 -m pytest tests/test_expansion_*.py`
- [ ] `python3 scripts/build_expansion_rc.py --out <dir>`
- [ ] `LEAK_SCAN.json` ok
- [ ] smoke_ok true
- [ ] No plaintext `dossiers/*.json` in RC tree
- [ ] No signing private keys in RC tree

## Gates

- [ ] Brutal state-survival + forced rollback
- [ ] Failure injection (staging / post-migration)
- [ ] Tamper rejection
- [ ] Missing/wrong key (no plaintext fallback)
- [ ] Low-disk estimate present
- [ ] Offline base operation
- [ ] Optional integrations degrade
- [ ] Repair preserves user data
- [ ] Uninstall preserves; purge requires confirmation
- [ ] Backup/restore roundtrip
- [ ] Concurrency stress
- [ ] Migration idempotence
- [ ] Startup transaction recovery
- [ ] Log redaction
- [ ] Windows static PASS; live classified honestly

## Promotion

Promote only with **zero BLOCKER / HIGH** release-critical issues.
Live Windows matrix may remain YELLOW if classified as infra/environment —
document in release notes.
