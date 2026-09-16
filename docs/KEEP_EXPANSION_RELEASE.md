# Keep Expansion — Release & Update

**Status:** P3  
**Channels:** `dev` | `public` | `protected`

## Release checklist

1. All Expansion tests green on clean checkout.
2. Product dossiers validated (`product/dossiers/*.json` SoT).
3. `build_protected_release` smoke_ok.
4. Manifest signature verifies with release public key.
5. Tampered bundle / wrong key rejected safely.
6. Optional capabilities (Video Studio, HA, Discord, n8n) degrade to
   UNAVAILABLE/LIMITED without breaking foundation.
7. Core-only install path unchanged; private Keep untouched; Hunter Pack separate.

## Update flow (protected)

```text
fetch signed manifest
  → verify signature
  → download package
  → verify artifact hashes + signature
  → stage under user packages/
  → snapshot user state
  → apply schema migrations
  → switch current version pointer
  → semantic health (re-verify staged package)
  → commit
```

Failure at any step after staging:

```text
restore previous known-good package pointer
  → keep / restore state snapshot if needed
  → report repair/reinstall (never wipe user data)
```

API: `expansion.release.update.apply_protected_update` /
`rollback_to_previous`.

## Package vs user vs secrets

| Tree | Contents |
|---|---|
| Product package | manifest, runtime, `protected-bundle.enc`, public verify key |
| User data | memory, journal, diary, relationships, jobs, living dossier, preferences |
| Secrets | platform-protected key blobs (bundle key, etc.) |

## Smoke tests (protected artifact)

Must prove:

- five agents’ dossiers decrypt/load
- Codec/runtime context assembles without plaintext dossier leak in release tree
- emotion / relationships / journal / diary / jobs still function on user state
- rooms + Video Studio capability probe resolve
- optional integrations degrade safely
- restart persistence (user state) intact
- update + rollback
- tampered package rejected
- wrong/missing key rejected
- Core-only unaffected

## Versioning

Expansion package version (`EXPANSION_VERSION`) moves independently of Core.
Schema versions in `expansion.versions` gate migrations. Keep previous
known-good protected package under `package_versions_root` for rollback.
