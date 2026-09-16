# Keep Expansion — Build Pipeline

**Status:** P3 productization  
**Canonical product data (dev):** `expansion/product/dossiers/*.json`  
**Release format:** encrypted `protected-bundle.enc` (dossiers never shipped plaintext)

## Two channels

### Development

```text
source → tests → normal runnable tree
```

- Product dossiers remain plaintext JSON under `product/dossiers/` (SoT).
- `canonical_dossiers.py` loads/validates only.
- Diagnostics and debug Expansion APIs may be enabled.

```bash
python3 scripts/build_expansion_release.py --channel dev --out /tmp/exp-dev
```

### Protected release

```text
private source
  → tests
  → (optional compile of priority modules — evaluated, not blind)
  → minify/harden frontend (no source maps)
  → package protected resources
  → compress + AES-256-GCM encrypt
  → Ed25519-sign manifest
  → smoke-test actual protected artifact
  → publish
```

```bash
python3 scripts/build_expansion_release.py --channel protected --out /tmp/exp-prot --ui ui
```

Reproducible from a clean checkout plus CI secrets (signing private key,
optional). Bundle encryption keys are random high-entropy secrets stored via
`KeyProvider` — never embedded in the package tree, BAT, PowerShell, JS, or logs.

## Layout (protected artifact)

```text
<out>/
  PACKAGE_MANIFEST.json      # signed
  protected-bundle.enc       # AEAD ciphertext
  protected-bundle.meta.json # non-secret metadata
  signing-public.pem         # verification key (public)
  runtime/ui/                # hardened frontend (optional)
```

User state stays under XDG-style roots (`~/.config/otacon/expansion`,
`~/.local/share/otacon/expansion`) and is never packed into the product bundle.

## Python entrypoints

| Module | Role |
|---|---|
| `expansion.release.build` | `build_dev_tree` / `build_protected_release` |
| `expansion.protected.bundle` | Collect product members → encrypt |
| `expansion.protected.signing` | Ed25519 sign/verify |
| `expansion.protected.keys` | Platform key provider |
| `expansion.release.frontend` | Map strip / secret scan |
| `expansion.release.compile_eval` | Priority-module compile policy |

## CI expectations

1. Run Expansion test suite (`tests/test_expansion_*.py`).
2. Build protected artifact in a clean workspace.
3. Smoke: decrypt Aria dossier, verify manifest signature, reject tampered bytes.
4. Publish artifact + public verification key (private signing key stays in CI secrets).
