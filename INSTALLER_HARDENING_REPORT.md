# Installer Hardening Report

**Date:** 2026-09-13  
**Branches:** `hardening/installer-public` in:

- `otacons-ai-ecosystem` (`/mnt/data/tmp/otacon-public`)
- `AI9` (`/root/AI9`)
- `otacon-voice-trainer` (`/root/otacon-voice-trainer`)
- `otaconskeep-site` (`/root/otaconskeep-site`)

**Backups:** local git branches/tags `backup/pre-installer-hardening-20260913` / `backup-pre-hardening-*` created before edits.

**Principle applied:** a running process, open port, installed dependency, or HTTP health endpoint alone does **not** count as successful installation. READY/ONLINE requires functional end-to-end proof for required selected components.

---

## Summary table

| ID | Issue | Severity | Verified Before Change | Fix | Files Changed | Validation | Status |
| -- | ----- | -------- | ---------------------- | --- | ------------- | ---------- | ------ |
| 1 | Otacon LAN bind truth + security | P0 | YES — `server.py` hardcoded `127.0.0.1`; installer defaulted `OTACON_CHAT_HOST=0.0.0.0` and printed LAN URL; no auth; path traversal on `serve`/`/api/save` | Honor `OTACON_HOST` + `OTACON_LAN_MODE`; default local bind; LAN opt-in with Bearer token; protect mutating APIs; confine UI/config paths; show LAN URL only when LAN enabled; firewall tips | `installer/server.py`, `installer/security.py`, `install_otacon.sh`, site HTML | Unit tests + local/LAN HTTP acceptance (401 without token; path traversal 404; forbidden save root) | **PASS** (LAN remote-machine bind not exercised on this host) |
| 2 | Windows → Bash env propagation | P0 | YES — `ENV= curl \| bash` on bat lines | Download to temp file, verify non-empty/shebang, `env … bash installer.sh`; propagate supported vars | `install_otacon.bat` | Simulated env visibility + failed-download non-zero | **PASS** (logic tested; full Windows WSL not available here) |
| 3 | False-success READY banners | P0 | YES — always printed SYSTEM READY / AI9 ONLINE | READY(0) / DEGRADED(2) / FAILED(1); gate banners on required validation | `install_otacon.sh`, `install_otacon.bat`, `install_ai9.sh`, `install_voice_trainer.sh` | State-machine simulation: broken model→FAILED, optional fail→DEGRADED, clean→READY | **PASS** |
| 4 | Real Otacon E2E LLM test | P0 | YES — installer only hit `/api/branding` | `validate-e2e-chat` POST `/api/chat_with_agent` with `OTACON_READY_<token>`; required when Default Model selected | `installer/validate_e2e_chat.py`, `installer/backend_entry.py`, `install_otacon.sh` | Module import + wiring; live inference not run in this session (would need Otacon on :5757 with selected model) | **PARTIAL** |
| 5 | Genome Docker group fresh install | P0 | YES — `usermod` then plain `docker` | `docker_cmd` via `sg docker`/`sudo`; re-exec under `sg docker`; user notified to open new shell later | `install_voice_trainer.sh` | `bash -n`; logic review | **PASS** (fresh Ubuntu Docker path not re-run on this host) |
| 6 | WSL distro targeting (Genome) | P0 | YES — bat used default distro | Reuse/improve Ubuntu finder; `-d "%UBUNTU_NAME%"`; skip docker-desktop; report selected distro | `install_voice_trainer.bat`, `deploy/find-ubuntu.ps1` (VT + ecosystem) | Script review + shared finder | **PASS** (multi-distro Windows not available here) |
| 7 | AI9 real E2E image inference | P1 | YES — ONLINE after HTTP/GPU only | Bundled `installer_probe.png`; POST `/colorize-image-data`; decode/dimension checks; gate ONLINE | `install_ai9.sh`, `backend/testdata/installer_probe.png` | `bash -n`; code path present | **PARTIAL** (needs Windows+GPU runtime) |
| 8 | SHA256 integrity for AI9 assets | P1 | YES — ZIP open only | `backend/checksums.json` + verify/retry/delete on mismatch | `backend/checksums.json`, `install_ai9.sh` | Schema present; hashes **PENDING** until release digests published | **PARTIAL** |
| 9 | Pin public releases | P1 | YES — always `main` | `release.json` + `installer/release_meta.py`; docs for tag pinning; main still allowed for dev | `release.json`, `installer/release_meta.py`, README | Files present | **PARTIAL** (mechanism only; no cut release tag yet) |
| 10 | Pin Python/runtime deps (AI9) | P1 | YES — any ≥3.10 | Prefer Python 3.12; `requirements-lock.txt` + tightened requirements | `install_ai9.sh`, `backend/requirements*.txt` | `bash -n` | **PASS** (runtime install not executed here) |
| 11 | Formal Linux support matrix | P1 | YES — any Debian-like claimed | supported / best_effort / unsupported with override | `install_otacon.sh`, site, README | Classifier exercised via script parse | **PASS** |
| 12 | Tauri/native optional (CORE default) | P1 | YES — `OTACON_BUILD_NATIVE=1` default | Default profile CORE (`BUILD_NATIVE=0`); DESKTOP opt-in; skip WebKit apt pkgs when Core | `install_otacon.sh`, site | Default inspection | **PASS** |
| 13 | Capability-aware UI/API | P2 | YES — UI assumed features work | `/api/capabilities`; wizard gates STT/image/video | `installer/server.py`, `ui/wizard.js`, `ui/index.html` | Capabilities endpoint in local server test | **PASS** |
| 14 | STT honesty | P2 | YES — package ≠ READY; provider stub | Capabilities mark unavailable; `validate-stt --real` required for READY; FasterWhisper health honest | `validate_stt.py`, `install_otacon.sh`, `core/stt.py` (unchanged stub) | Health returns `STT_MODEL_MISSING` without package | **PASS** (real Whisper model load still not implemented upstream) |
| 15 | WSL preflight / terminate target | P2 | PARTIAL | Prefer `wsl --terminate <distro>` over `--shutdown`; report selected Ubuntu; basic WSL checks | `install_otacon.bat`, `install_voice_trainer.bat` | Script review | **PARTIAL** |
| 16 | LAN/firewall behavior | P2 | YES — advertised without bind/auth | Verify bind mode; firewall examples; correct LAN URL only when enabled | `install_otacon.sh`, `server.py`, site | Local acceptance | **PASS** |
| 17 | AI9 HTTPS/certificate UX | P2 | YES — thin messaging | Clear self-signed one-time trust; no false security claims | `install_ai9.sh`, `ai9/index.html` | Copy review | **PASS** |
| 18 | Firefox extension persistence | P2 | YES — temporary add-on | Explicit non-persistent; browser integration never READY; DEGRADED if Firefox missing | `install_ai9.sh`, site | Copy + status model | **PASS** (signed persistent path still unavailable) |
| 19 | Website claim audit | P3 | YES — LAN/docs drift | Aligned LAN, profiles, OS matrix, uninstall, AI9 claims | `otaconskeep-site/*`, README | Grep/review | **PASS** |
| 20 | Clarify uninstall | P3 | YES — ambiguous | Autostart-only vs full uninstall commands documented | `uninstall_otacon.bat`, site, README | Review | **PASS** |
| 21 | Hardware/resource thresholds | P4 | PARTIAL — detect only | PASS/WARNING/FAIL for RAM/disk/network/port | `install_otacon.sh` | Logic review | **PASS** |
| 22 | Logs + doctor | P4 | YES — missing | Timestamped install log; `otacon doctor`; `ai9_doctor.py` | `install_otacon.sh`, `installer/doctor.py`, `tools/ai9_doctor.py` | Doctor smoke ran | **PASS** |

---

## Remaining known limitations

- AI9 `checksums.json` digests are still `PENDING` until release builds publish real SHA256 values for generator / RealESRGAN / denoiser weights.
- Faster-Whisper **model lifecycle** in `core/stt.py` is still incomplete upstream (`STT_MODEL_LOADING` / raises on transcribe). Installer correctly refuses to mark STT READY.
- Public installers still default `release.json` → `main` until a versioned tag is cut and `ecosystem_ref` updated.
- Otacon E2E chat acceptance was not executed against a full fresh install on this machine (port 5757 currently serves a non-Otacon 404; doctor correctly FAILs branding).
- Genome / AI9 full GPU container and Windows Git Bash paths were not re-run end-to-end on this Linux host.
- CORS remains permissive on localhost mode; LAN mode tightens CORS and requires Bearer auth for protected routes.
- SQLite `MemoryStore` is not thread-safe if a threaded server is used; production path uses sequential `HTTPServer` under systemd.

## Unsupported configurations

- Ubuntu older than 22.04 for native/desktop WebKit/Tauri builds (override: `OTACON_ALLOW_UNSUPPORTED_OS=1` for best-effort Core web).
- Non-Debian-family hosts for Otacon/Genome public installers.
- AI9 without NVIDIA GPU / suitable driver (installer fails closed).
- Genome Voice Trainer without NVIDIA + working `docker --gpus all`.
- Claiming persistent Firefox AI9 extension without signing (not supported).

## Manual steps still required

- Windows: first-time Ubuntu username/password inside WSL (unchanged).
- AI9: one-time browser trust of self-signed cert; temporary Firefox add-on load after each Firefox restart.
- LAN firewall rules: installer prints examples; admin must apply them.
- After Docker group add: open a new interactive shell for plain `docker` without `sg`/`sudo`.
- Publishing release: set git tags + fill SHA256 digests in `release.json` / `checksums.json`.

## Regression risks

- Default `OTACON_BUILD_NATIVE=0` changes prior default (was 1). Desktop users must set `OTACON_PROFILE=desktop` or `OTACON_BUILD_NATIVE=1`.
- Default bind is now localhost; users who relied on accidental LAN advertising must opt in with `OTACON_LAN_MODE=1` and pass the token.
- Installer exit code `2` (DEGRADED) may break wrappers that assumed only 0/1.
- Windows bat now depends on download-to-temp; offline/airgapped installs need a local script copy.
- Stricter READY gates may cause previously “green” installs to report FAILED until Ollama/model/inference actually work — intentional.

## Test matrix results

| Environment / scenario | Result |
| --- | --- |
| Security unit tests (`tests/test_installer_security.py`) | **PASS** (7/7) |
| Local bind + branding + capabilities | **PASS** |
| Path traversal rejection | **PASS** |
| `/api/save` arbitrary path rejection | **PASS** |
| LAN unauthenticated protected API → 401 | **PASS** |
| Windows env propagation pattern (simulated) | **PASS** |
| Failed download does not execute installer (simulated) | **PASS** |
| READY/DEGRADED/FAILED state machine (simulated) | **PASS** |
| `bash -n` all public installers | **PASS** |
| `otacon doctor` smoke | **PASS** (correctly reported non-Otacon on :5757) |
| Ubuntu 22.04/24.04 clean full install | **NOT RUN** (no clean VMs in session) |
| Windows 11 + WSL2 multi-distro | **NOT RUN** |
| Genome fresh Docker usermod path | **NOT RUN** (logic reviewed) |
| AI9 RTX 30/40/50 full inference | **NOT RUN** |
| Corrupted AI9 model retry | **NOT RUN** (code path present; hashes PENDING) |

## Recommended next improvements

1. Cut `v0.1.0` tags and populate SHA256 digests for AI9 weights and any pinned ecosystem artifacts.
2. Implement real Faster-Whisper model download/load/transcribe path, then keep `--real` gate.
3. Add CI jobs: Ubuntu 22.04/24.04 installer dry-runs; bat syntax via CI Windows runners; security unittest.
4. Optional signed Firefox extension / policy-based enterprise install.
5. Make `MemoryStore` check_same_thread=False or per-request connections if moving to `ThreadingHTTPServer`.
6. Expand `otacon doctor` to invoke `validate-e2e-chat` when a model is configured.

---

## Qualitative readiness assessment

No statistical success percentage is claimed — automated multi-distro install telemetry was not generated in this session.

| Surface | Assessment |
| --- | --- |
| Linux Otacon | **Much improved for strangers** — Core default, localhost-safe, real READY gates, doctor/logs, OS honesty. Remaining risk: first full clean-VM soak + live E2E on each LTS. |
| Windows/WSL Otacon | **Improved** — env propagation + terminate-target + Ubuntu selection. Remaining risk: real Windows soak for resume/RunOnce paths. |
| Genome Voice Trainer | **Improved** — Docker group session fix + Ubuntu targeting. Remaining risk: fresh GPU host soak. |
| AI9 | **Improved honesty** — E2E probe + status model + Python 3.12 preference + checksum hooks. Remaining risk: PENDING hashes + Windows GPU execution. |
| Full ecosystem | **Closer to trustworthy public installers**, but not “fire-and-forget certified” until clean-matrix soaks fill the NOT RUN rows above. |

---

## Exit code scheme (documented)

| Code | Meaning |
| --- | --- |
| 0 | READY — required selected components passed functional validation |
| 2 | DEGRADED — core works; optional component failed |
| 1 | FAILED — required component failed |
| 42 | Otacon WSL systemd just enabled (Windows bat terminates distro and reruns) |
| 75 | Genome WSL systemd just enabled (same pattern) |
