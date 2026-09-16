# Keep Expansion — Security Model

**Status:** P3 protected distribution  
**Tamper response:** fail safe → preserve user data → offer repair/reinstall  
**Forbidden:** destructive anti-tamper, custom cryptography, plaintext package keys

## Goals

Make casual replication/modding of premium Expansion materials difficult while
keeping the product maintainable and recoverable.

Clean protection stack:

```text
private source
  → compile sensitive logic (optional, evaluated)
  → bundle/minify frontend
  → strip source maps / debug metadata
  → encrypt protected resources (AES-256-GCM)
  → sign manifest/artifacts (Ed25519)
  → machine-protect local keys (DPAPI / permissioned secrets)
  → verify at install / update / runtime
```

## Cryptography

| Use | Algorithm |
|---|---|
| Protected bundle | **AES-256-GCM** (XChaCha20-Poly1305 reserved in contract) |
| Manifest signing | **Ed25519** |
| Password-derived unlock (optional adjunct) | **Argon2id** + unique random salt |

Rules:

- No custom crypto.
- Bundle key = independent high-entropy random secret.
- Owner password must never be the sole package key.
- Manifest must never contain `key` / `password` / `secret` / `private_key`.

## What goes in the protected bundle

Product-only:

- Canonical dossiers (from dev JSON SoT)
- Persona / system prompt resources (when present under `product/prompts`)
- Relationship / emotion package stamps
- Premium workflow definitions / private templates (when present)
- Selected protected assets

Never:

- User memories, journals, diaries, relationships, jobs, living dossiers
- Credentials, tokens, webhook URLs
- Private Keep lore or LAN topology

## Local key protection

`expansion.protected.keys.KeyProvider`:

| Platform | Provider |
|---|---|
| Linux / dev | `PermissionedFileKeyProvider` — `secrets/` mode `0700`, files `0600` |
| Windows | `WindowsDpapiKeyProvider` — DPAPI when `win32`; file fallback for cross-dev tests |

**P3 status — Linux local keys: YELLOW (not final).** Mode `0600` is permissions
protection, not OS-bound secret storage. Acceptable for this milestone; later
candidates include system keyring, TPM-backed secrets, systemd credentials, or
libsecret depending on deployment. Windows DPAPI remains the stronger
OS-bound path.

Do not store plaintext keys in BAT, PowerShell, Python source, JavaScript,
JSON configs, env files, or logs.

## Signing / integrity

`PackageManifest` covers:

- package ID / product
- expansion version + agent schema version
- Core minimum version
- build ID + release channel
- component / artifact hashes (including encrypted bundle)
- signature + signing key id

Verify before install and when switching package versions. Hash mismatch or
bad signature → reject update, keep prior known-good package, leave user data
untouched.

## Frontend

Protected builds:

- no `.map` files
- strip `sourceMappingURL`
- scan for embedded secret patterns (fail build on hit)
- no debug endpoints that return system prompts / package keys

Developer builds may retain diagnostics.

## Compile policy

See `expansion.release.compile_eval`. Priority candidates (runtime, emotion,
relationship math, protected loader, entitlement) may be compiled in CI later.
Do not sacrifice unit-testability for obfuscation depth. No anti-debug games.
