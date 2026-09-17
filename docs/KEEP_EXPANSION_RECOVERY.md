# Keep Expansion — Recovery

## Transactional updates

Phases (persisted under `user_migrations/transactions/`):

```text
precheck → download → signature_verification → package_decryption →
staging → migration → service_startup → semantic_health →
restart_health → commit
```

On reboot/interrupt, `recover_active_transaction()` loads `ACTIVE.json` and
either **RESUME** or **ROLL BACK** via `decide_resume_or_rollback()` — never
guesses.

## Forced update failure

`transactional_update(..., inject_fail_at=<phase>)` simulates failure.
Expected: `action=rolled_back`, user state intact, previous package pointer
restored when available.

## Repair

```python
from expansion.qualify.repair import repair_expansion
repair_expansion(channel='dev')  # or protected + package_dir
```

CLI-oriented entry: use acceptance/repair APIs; product CLI wiring may call
`repair_expansion`.

Repair may restore product artifacts / re-run idempotent migrations.
Repair must **not** erase memories, relationships, journal, diary, living
dossier, jobs, or preferences.

## Uninstall vs purge

| Mode | Behavior |
|---|---|
| `uninstall_expansion()` | Remove staged packages; **preserve** user state |
| `purge_expansion_user_data(confirmation='PURGE_EXPANSION_USER_DATA')` | Destroy user Expansion data |

Never conflate uninstall with purge.

## Tamper / wrong key

Protected verify fails → reject update, preserve Core + user data, offer
repair/reinstall. No plaintext dossier fallback when the bundle key is
missing.
