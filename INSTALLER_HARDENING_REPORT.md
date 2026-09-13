# Installer Hardening Report — Release Validation

**Date:** 2026-09-13  
**Branch:** `hardening/installer-public` (all four repos)  
**Mode:** feature-frozen remediation + release validation  
**Do not merge to main / do not push production release without explicit approval.**

---

## Preserved hardening commits (pre-validation)

| Repository | Commit SHA | Message |
| --- | --- | --- |
| otacons-ai-ecosystem | `e830a3094cf2aec7353de2985a5cbcba7e86b8dd` | Harden public Otacon installer for safe READY/LAN installs |
| AI9 | `cca92c4e2f208eb7a50880c0459cafd0b6964a2b` | Harden AI9 installer with real READY gates and integrity hooks |
| otacon-voice-trainer | `78b47ec194c43c6f88e9a5c4b4e5ef6c14235351` | Harden Genome installer Docker group and Ubuntu WSL targeting |
| otaconskeep-site | `70c762ef6fdec602563252427d70399109ce52f1` | Align public site with hardened installer behavior |

Backup tags/branches from pre-hardening remain intact (`backup/pre-installer-hardening-*`, `backup-pre-hardening-*`).

---

## AI9 SHA256 asset resolution

Canonical sources taken from `install_ai9.sh` / upstream sync path.

| Asset | Bytes | SHA256 | Source | Status |
| --- | ---: | --- | --- | --- |
| `generator.zip` (colorizer weights) | 128960375 | `087e6a0bc02770e732a52f33878b71a272a6123c9ac649e9b5bfb75e39e5c1d5` | Google Drive id `1qmxUEKADkEM4iYLp1fpPLLKnfZ6tcF-t` (`gdown`) | **RESOLVED** |
| `RealESRGAN_x4plus_anime_6B.pt` | 17944851 | `6a276ed556d0ee68b6a1e887f91dab6dd67fb96d2cbb0690dcaddb4830836a27` | Upstream `gilgamesh117/Manga-Colorizer` `Backend/networks/` | **RESOLVED** |
| `denoising/models/net_rgb.pth` | 3435567 | `0fe98bfd2ac870b15f360661b1c4789eecefc6dc2e4462842a0dd15e149a0433` | Upstream `Backend/denoising/models/` | **RESOLVED** |
| Separate colorizer remote file | — | — | Colorizer payload **is** `generator.zip` | N/A (not a distinct remote artifact) |

Checksum mismatch rejection test (installer verify helper): corrupt RealESRGAN and generator copies → mismatch detected, file deleted, exit non-zero. **PASS**

---

## Summary issue table (post-validation)

| ID | Issue | Severity | Verified Before Change | Fix | Files Changed | Validation | Status |
| -- | ----- | -------- | ---------------------- | --- | ------------- | ---------- | ------ |
| 1 | LAN bind/auth/paths | P0 | YES | Local default + LAN opt-in Bearer auth + path confinement | `installer/security.py`, `server.py`, `install_otacon.sh` | 11/11 LAN suite | **PASS** |
| 2 | Windows env propagation | P0 | YES | Temp download + `env … bash` | `install_otacon.bat` | Simulated env + failed download | **PASS** (full Windows **NOT RUN**) |
| 3 | False READY banners | P0 | YES | READY/DEGRADED/FAILED 0/2/1 | installers | Clean READY=0; DEGRADED=2; FAILED=1 observed | **PASS** |
| 4 | E2E LLM proof | P0 | YES | `validate-e2e-chat` + retries | `validate_e2e_chat.py`, installer | Clean Ubuntu ISO: READY after E2E PASS | **PASS** |
| 5 | Docker group same-session | P0 | YES | `sg docker` / re-exec | `install_voice_trainer.sh` | `sg docker` works when member; plain same-shell needs sg | **PASS** (logic) |
| 6 | WSL Ubuntu targeting | P0 | YES | `find-ubuntu.ps1` + `-d` | VT bat + deploy | Script review | **PASS** (Windows **NOT RUN**) |
| 7 | AI9 E2E image | P1 | YES | Probe + ONLINE gate | `install_ai9.sh`, testdata | Windows/GPU path | **NOT RUN** |
| 8 | AI9 SHA256 | P1 | YES | Digests published | `checksums.json` | Match + mismatch tests | **PASS** |
| 9–12 | Pinning / Python / OS / CORE | P1 | YES | As implemented | release.json, installers, site | Review + Core clean path | **PASS** / PARTIAL |
| 13–22 | Caps/STT/docs/doctor/etc. | P2–P4 | YES | As implemented | multiple | See evidence below | Mixed |

---

## Validation evidence

### Otacon Linux — clean Ubuntu 24.04 (disposable Docker `otacon-rv-iso`)

| Test | Environment | Command/test | Expected | Observed | Exit | Status |
| --- | --- | --- | --- | --- | ---: | --- |
| Missing `zstd` blocks Ollama | Ubuntu 24.04 container (first attempt) | `bash install_otacon.sh` Core | Ollama installs | Ollama extractor required zstd → FAIL | 1 | **FAIL** (found) → fixed by adding `zstd` to apt |
| Core clean install | Isolated Ubuntu 24.04, no host network, no preinstalled Ollama | Core profile, VT=0, model=`qwen2.5:1.5b` | READY after E2E | Model pulled; UI up; first E2E flaky then fixed with retries; validate-memory argv bug caused DEGRADED | 1 then 2 | **PARTIAL** → fixed |
| READY after fixes | Same container, synced fixes | Re-run installer | READY 0 | `Final state: READY (exit 0)`, E2E PASS | 0 | **PASS** |
| Real `/api/chat_with_agent` | Same | POST chat + validate-e2e-chat | Token in response | `OTACON_READY_*` returned | 0 | **PASS** |
| `otacon doctor` | Same | `~/.local/bin/otacon doctor` | Useful status | Passes branding/ollama/config; WARNING no systemd | 0 | **PASS** |
| Restart recovery | Kill server + rerun installer | Service returns | Stale PID skipped relaunch (bug) then fixed with branding check | After PID fix: READY 0 | 0 | **PASS** |
| Idempotent reinstall | Second/third runs | Reuse deps/models | No redownload of model; E2E PASS | `Ollama already installed`, `Model ready` without full re-pull | 0/2→0 | **PASS** |
| Systemd reboot simulation | Container without systemd | — | Service survives reboot | No systemd in container | — | **NOT RUN** (no systemd) |

### Otacon Windows

| Test | Status |
| --- | --- |
| Clean Win11 + WSL2 + `.bat` path | **NOT RUN** — no Windows/WSL host available |
| Env options from bat into WSL | **PASS** (Linux simulation of `env … bash` pattern only) |
| Distro terminate vs shutdown | **NOT RUN** on Windows (script reviewed) |

### Genome

| Test | Environment | Expected | Observed | Exit | Status |
| --- | --- | --- | ---: | --- |
| Docker daemon unavailable | `DOCKER_HOST=tcp://127.0.0.1:1` | Fail | Cannot connect | 1 | **PASS** |
| Same-session docker via `sg` | user `otaconvt` | `sg docker` works | `sg=0` when in group | 0 | **PASS** |
| Fresh Docker install end-to-end + NVIDIA toolkit | — | Full READY | Not executed (host already has Docker; nested GPU docker not run) | — | **NOT RUN** |

### AI9

| Test | Status |
| --- | --- |
| Non-Windows gate | **PASS** — exit **1** with clear message |
| SHA256 resolve + mismatch reject | **PASS** |
| Clean Windows NVIDIA install + E2E image + ONLINE | **NOT RUN** (installer is Windows Git Bash only) |
| Occupied port / corrupt model on live AI9 | **NOT RUN** (no Windows AI9 runtime) |

### Failure semantics (exit contract)

| Scenario | Expected | Observed | Status |
| --- | --- | --- | --- |
| Ollama/model pull fail | FAILED / 1 | Host-network collision pull fail → FAILED 1; also Ollama-down E2E → 1 | **PASS** |
| E2E missing token (first flaky run) | FAILED / 1 | FAILED 1, no SYSTEM READY | **PASS** |
| Optional validator fail | DEGRADED / 2 | validate-memory argv bug → DEGRADED 2 | **PASS** (then fixed) |
| Clean success | READY / 0 | READY 0 | **PASS** |
| State machine matrix | 0/2/1 mapping | Simulated matrix matched | **PASS** |

### LAN security

| Test | Expected | Observed | Status |
| --- | --- | --- | --- |
| Local bind 127.0.0.1 | local mode | PASS | **PASS** |
| Localhost works | branding OK | PASS | **PASS** |
| Traversal rejected | 404 | PASS | **PASS** |
| Arbitrary save rejected | 400 OUTPUT_PATH_FORBIDDEN | PASS | **PASS** |
| Allowed save OK | 200 | PASS | **PASS** |
| LAN missing token | 401 | PASS | **PASS** |
| LAN wrong token | 401 | PASS | **PASS** |
| LAN correct token save | 200 | PASS | **PASS** |
| Token not in branding JSON | absent | PASS | **PASS** |
| Remote LAN machine connect | local rejects / LAN accepts | Same-host suite only | **PARTIAL** |

### Documentation audit

| Claim area | Match? | Notes |
| --- | --- | --- |
| Core default (no Tauri) | YES | Site + installer |
| LAN explicit opt-in + Bearer | YES | Site advanced section |
| OS matrix | YES | 22.04/24.04 supported; Mint/Pop best-effort |
| STT honesty | YES | not_configured / requires provider |
| Uninstall autostart-only | YES | clarified; full uninstall manual |
| Backup/restore “Available now” | WAS OVERSTATED | Corrected to split auto-start uninstall vs backup/restore |
| Firefox temporary | YES | AI9 page |
| READY/DEGRADED/FAILED | YES | Documented |

---

## Fixes discovered during release validation (blocker-class)

1. **`zstd` missing from Core apt list** — Ollama install failed on clean Ubuntu 24.04.  
2. **E2E flaky under agent personality** — strengthened prompt + retries.  
3. **`validate-memory` argv bug** — caused false DEGRADED.  
4. **Stale PID file** — installer believed server was up after kill; now requires branding health.

---

## Release blockers

### BLOCKER

| Item | Why |
| --- | --- |
| Windows Otacon `.bat` path untested on real Win11/WSL | Required acceptance matrix item; environment unavailable here |
| AI9 clean Windows+GPU ONLINE path untested | Installer refuses non-Windows; no disposable Windows GPU host |
| Public installers still point at GitHub `main` | Hardening is only on `hardening/installer-public` until merge/release; strangers curling `main` do **not** get these fixes |

### SHOULD FIX

| Item | Why |
| --- | --- |
| Systemd reboot soak on real Ubuntu VM (not Docker) | Container lacked systemd; auto-start after reboot not proven |
| Genome fresh-Docker + NVIDIA toolkit one-shot on clean machine | Only `sg docker` unit proof here |
| Publish release tag + pin `release.json` refs away from floating `main` | Mechanism exists; not cut |
| E2E chat still model-temperature sensitive | Retries help; consider lower temp / dedicated test agent later |

### ACCEPTED LIMITATION

| Item | Why |
| --- | --- |
| No statistical install-success % | No repeated automated multi-sample campaign |
| AI9 Firefox remains temporary unsigned add-on | Signing not practical now; docs honest |
| Faster-Whisper real model lifecycle incomplete upstream | Correctly not marked READY |
| Docker container validation ≠ full bare-metal Ubuntu LTS | Closest disposable clean env available |
| LAN remote-machine probe | Same-host bind/auth suite used |

---

## Qualitative readiness (no fake percentages)

| Surface | Assessment |
| --- | --- |
| Linux Otacon Core | **Release-candidate for Linux Core** after merge — clean Ubuntu 24.04 isolated install reached READY with real inference; several blockers found and fixed in-branch |
| Windows/WSL Otacon | **Not validated** — BLOCKER |
| Genome Voice Trainer | **Partially validated** — docker group logic OK; full GPU fresh path NOT RUN |
| AI9 | **Checksums ready; runtime NOT RUN** on Windows GPU |
| Full ecosystem | **Do not ship from `main` until hardening branch is merged/tagged and Windows/AI9 soaks exist** |

---

## Commands to inspect trees after validation commits

```bash
cd /mnt/data/tmp/otacon-public && git log -2 --oneline && git status -sb
cd /root/AI9 && git log -2 --oneline && git status -sb
cd /root/otacon-voice-trainer && git log -2 --oneline && git status -sb
cd /root/otaconskeep-site && git log -2 --oneline && git status -sb
```
