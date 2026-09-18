#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
#  OTACONSKEEP // OTACON AI ECOSYSTEM -- OTACON CORE
#  AUTOMATED ONE-COMMAND BOOTSTRAP + NATIVE BUILDER (free, full source)
#
#  Designed & Engineered by Antonio G. Garcia
#  "Built for the Keep."
#  Community, support, and Otaconskeep Services: https://discord.gg/cZDeqECzX
# ==============================================================================
#
# Target:
#   Debian / Ubuntu-family Linux
#
# What this installer does:
#   - Checks the operating system and hardware
#   - Detects NVIDIA GPU, VRAM, CPU, RAM, and free storage
#   - Selects the same general LLM tier used by Otacon's hardware planner
#   - Installs missing OS build dependencies
#   - Installs Git / Python tooling if missing
#   - Clones or updates the public Otacon repository
#   - Creates/reuses an isolated Python virtual environment
#   - Installs lightweight runtime/build Python dependencies
#   - Handles Python 3.13+ audioop compatibility
#   - Runs the full unit test suite
#   - Runs deterministic Otacon validation commands
#   - Packages installer/backend_entry.py as installer/bin/otacon-backend
#   - Installs Rust / Cargo if missing
#   - Installs Tauri CLI v2 if missing
#   - Builds the native .deb package
#   - Optionally installs the generated .deb
#   - Launches the setup wizard and checks http://127.0.0.1:5757
#     (legacy wizard default 8787 is retired — Core/canonical port is always 5757)
#   - Installs Ollama + a VRAM-sized default chat model (skip: OTACON_INSTALL_DEFAULT_MODEL=0)
#   - Installs Genome Voice Trainer when a GPU path is available (skip: OTACON_INSTALL_VOICE_TRAINER=0)
#
# Rerunnable:
#   - Existing repo -> fast-forward update
#   - Existing venv -> reused
#   - Existing Rust/Cargo/Tauri -> reused
#   - Existing OS packages -> apt skips them
#
# Environment overrides:
#   OTACON_INSTALL_DIR="$HOME/otacon-ai-ecosystem"
#   OTACON_PROFILE=core|desktop     # core (default): server+Ollama; desktop: +Rust/Tauri .deb
#   OTACON_BUILD_NATIVE=0           # default 0 for CORE; set 1 or use profile=desktop
#   OTACON_INSTALL_DEB=0
#   OTACON_LAUNCH_WIZARD=1
#   OTACON_INSTALL_STT=0
#   OTACON_RUN_TESTS=1
#   OTACON_INSTALL_VOICE_TRAINER=1   # set 0 to skip Genome Voice Trainer (GPU Piper)
#   OTACON_INSTALL_DEFAULT_MODEL=1   # set 0 to skip Ollama + VRAM-sized default chat model
#   OTACON_INSTALL_OLLAMA=...        # alias for OTACON_INSTALL_DEFAULT_MODEL (compat)
#   OTACON_LLM_MODEL=""             # override auto model (e.g. qwen2.5:7b)
#   OTACON_LAN_MODE=0               # set 1 to bind LAN (requires auth token)
#   OTACON_CHAT_HOST=127.0.0.1      # overridden to 0.0.0.0 when LAN mode=1
#   OTACON_RELEASE=                 # optional release tag; empty follows release.json / main
#   OTACON_ALLOW_UNSUPPORTED_OS=0   # set 1 to continue on unsupported distros
#   OTACON_INSTALL_PHASE=auto|privileged|user|finalize
#       auto       — interactive Linux (sudo may prompt on a real TTY)
#       privileged — MUST run as root (apt, wsl.conf, ollama pkg). Used by Windows via wsl -u root
#       user       — MUST run as normal user (repo, venv, models, config). No apt/sudo.
#       finalize   — MUST run as root (install systemd unit prepared by user phase)
#
# Windows one-click elevation (no NOPASSWD:ALL):
#   wsl -u root  → privileged
#   wsl (default user) → user
#   wsl -u root  → finalize
#
# Final states / exit codes:
#   READY    (0) — all required selected components passed functional validation
#   DEGRADED (2) — core works; an optional component failed
#   FAILED   (1) — a required component failed
# ==============================================================================

BRAND="ANTONIO G. GARCIA // OTACONSKEEP"
PRODUCT="OTACON AI ECOSYSTEM -- OTACON CORE"
TAGLINE="Built for the Keep."
DISCORD_URL="https://discord.gg/cZDeqECzX"

REPO_URL="https://github.com/Otaconskeep/otacons-ai-ecosystem.git"
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
VENV_DIR="$INSTALL_DIR/.venv"

OTACON_PROFILE="${OTACON_PROFILE:-core}"
case "${OTACON_PROFILE,,}" in
  desktop|native|full) DEFAULT_BUILD_NATIVE=1 ;;
  *) DEFAULT_BUILD_NATIVE=0 ;;
esac
BUILD_NATIVE="${OTACON_BUILD_NATIVE:-$DEFAULT_BUILD_NATIVE}"
INSTALL_DEB="${OTACON_INSTALL_DEB:-0}"
LAUNCH_WIZARD="${OTACON_LAUNCH_WIZARD:-1}"
INSTALL_STT="${OTACON_INSTALL_STT:-0}"
RUN_TESTS="${OTACON_RUN_TESTS:-1}"
INSTALL_VOICE_TRAINER="${OTACON_INSTALL_VOICE_TRAINER:-1}"
# Default Model = Ollama + VRAM-tier chat pull (normal Otacon install). Alias: OTACON_INSTALL_OLLAMA.
INSTALL_DEFAULT_MODEL="${OTACON_INSTALL_DEFAULT_MODEL:-${OTACON_INSTALL_OLLAMA:-1}}"
LAN_MODE="${OTACON_LAN_MODE:-0}"
# WSL: bind all interfaces so Windows can reach Core via localhost OR the WSL IP
# (localhost forwarding sometimes breaks → "connection refused" in the browser).
is_wsl_env() {
  grep -qi microsoft /proc/version 2>/dev/null && return 0
  [[ -e /proc/sys/fs/binfmt_misc/WSLInterop ]] && return 0
  return 1
}
WSL_ENV=0
if is_wsl_env; then WSL_ENV=1; fi
if [[ "$LAN_MODE" == "1" || "${LAN_MODE,,}" == "true" || "${LAN_MODE,,}" == "yes" || "${LAN_MODE,,}" == "lan" ]]; then
  LAN_MODE=1
  CHAT_HOST="${OTACON_CHAT_HOST:-0.0.0.0}"
else
  LAN_MODE=0
  if [[ "$WSL_ENV" == "1" ]]; then
    CHAT_HOST="${OTACON_CHAT_HOST:-0.0.0.0}"
  else
    CHAT_HOST="${OTACON_CHAT_HOST:-127.0.0.1}"
  fi
fi
# WSL nvidia-smi used to hang and freeze Codec; platform.detect() now abandons
# hung probes on a timeout, so we do NOT default-skip GPU inspection on WSL.
# Skipping made Codec/Setup lie with "no GPU detected" while Ollama still used CUDA.
OTACON_SKIP_NVIDIA_SMI="${OTACON_SKIP_NVIDIA_SMI:-0}"
CHAT_PORT="${OTACON_CHAT_PORT:-5757}"
VOICE_TRAINER_INSTALLER_URL="${OTACON_VOICE_TRAINER_URL:-https://raw.githubusercontent.com/Otaconskeep/otacon-voice-trainer/main/install_voice_trainer.sh}"
OLLAMA_ENDPOINT="${OTACON_LLM_ENDPOINT:-http://127.0.0.1:11434}"
ALLOW_UNSUPPORTED_OS="${OTACON_ALLOW_UNSUPPORTED_OS:-0}"
INSTALL_PHASE="${OTACON_INSTALL_PHASE:-auto}"
TARGET_USER="${OTACON_TARGET_USER:-}"
PRIV_MARKER_DIR="/var/lib/otacon"
PRIV_MARKER="$PRIV_MARKER_DIR/privileged-bootstrap.done"
SERVICE_DRAFT_NAME="otacon.service.draft"
# Install outcome tracking
REQUIRED_FAIL=0
OPTIONAL_FAIL=0
MODEL_OK=0
E2E_OK=0
TTS_E2E_OK=0
HEALTH_OK=0
VOICE_TRAINER_OK=0
INSTALL_LOG_DIR="${OTACON_INSTALL_LOG_DIR:-$HOME/.config/otacon/logs}"
mkdir -p "$INSTALL_LOG_DIR"
INSTALL_LOG="$INSTALL_LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$INSTALL_LOG") 2>&1

log()  { printf '\n\033[1;36m[AGG::OTACON]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[AGG::OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[AGG::WARN]\033[0m %s\n' "$*" >&2; }

# Machine-parseable stage markers for the Windows UI (and humans).
# Format: [STAGE] <id> <status> <detail>
stage() {
  local id="$1" status="$2"; shift 2
  printf '[STAGE] %s %s %s\n' "$id" "$status" "$*"
  printf '[AGG::PROGRESS] [%s] %s — %s\n' "$id" "$status" "$*"
}

# Durable exit marker for Windows (survives blank Start-Process ExitCode).
emit_phase_exit() {
  local rc="${1:-1}"
  local detail="${2:-}"
  stage "exit" "CODE" "${rc}${detail:+ ${detail}}"
  printf 'OTACON_PHASE_EXIT=%s\n' "$rc"
}

die()  {
  printf '\033[1;31m[AGG::FAIL]\033[0m %s\n' "$*" >&2
  printf '\033[1;31m[AGG::FAIL]\033[0m Failed stage near line %s. Log: %s\n' "${BASH_LINENO[0]:-$LINENO}" "$INSTALL_LOG" >&2
  printf 'Recovery: re-run this installer, or: PYTHONPATH=%s %s/bin/python -m installer.backend_entry doctor\n' \
    "${INSTALL_DIR:-$HOME/otacon-ai-ecosystem}" "${VENV_DIR:-$HOME/otacon-ai-ecosystem/.venv}" >&2
  emit_phase_exit 1 "die"
  exit 1
}

# Run a long command with heartbeats + hard timeout. Survives quiet tools (apt).
# Usage: run_watched TIMEOUT_SEC LABEL [--soft] -- command args...
# --soft: return non-zero instead of die() so callers can mark DEGRADED/REQUIRED_FAIL.
run_watched() {
  local timeout_sec="$1" label="$2"
  shift 2
  local soft=0
  if [[ "${1:-}" == "--soft" ]]; then soft=1; shift; fi
  if [[ "${1:-}" == "--" ]]; then shift; fi
  [[ "$#" -ge 1 ]] || die "run_watched: missing command for $label"

  local start_ts now elapsed last_hb=0
  start_ts="$(date +%s)"
  log "$label (timeout ${timeout_sec}s)"
  stage "watch" "START" "$label (timeout ${timeout_sec}s)"

  "$@" &
  local cmd_pid=$!

  while kill -0 "$cmd_pid" 2>/dev/null; do
    now="$(date +%s)"
    elapsed=$((now - start_ts))
    if (( elapsed >= timeout_sec )); then
      warn "$label exceeded ${timeout_sec}s — sending TERM to PID $cmd_pid"
      kill -TERM "$cmd_pid" 2>/dev/null || true
      sleep 5
      kill -KILL "$cmd_pid" 2>/dev/null || true
      wait "$cmd_pid" 2>/dev/null || true
      stage "watch" "FAIL" "$label timed out after ${timeout_sec}s"
      if [[ "$soft" -eq 1 ]]; then
        warn "$label timed out after ${timeout_sec}s"
        return 124
      fi
      die "$label timed out after ${timeout_sec}s with no completion. Last label: $label. Log: $INSTALL_LOG. Recovery: fix network/apt mirrors/sudo, then rerun the installer."
    fi
    if (( now - last_hb >= 15 )); then
      printf '[AGG::HEARTBEAT] %s still running — elapsed %sm%ss (pid %s)\n' \
        "$label" "$((elapsed / 60))" "$((elapsed % 60))" "$cmd_pid"
      last_hb=$now
    fi
    sleep 2
  done

  local rc=0
  wait "$cmd_pid" || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    stage "watch" "FAIL" "$label exit=$rc"
    if [[ "$soft" -eq 1 ]]; then
      warn "$label failed with exit code $rc"
      return "$rc"
    fi
    die "$label failed with exit code $rc. Log: $INSTALL_LOG"
  fi
  stage "watch" "PASS" "$label"
  ok "$label"
  return 0
}

apt_has_lock() {
  local f
  for f in \
    /var/lib/dpkg/lock-frontend \
    /var/lib/dpkg/lock \
    /var/lib/apt/lists/lock \
    /var/cache/apt/archives/lock
  do
    if [[ -e "$f" ]] && command_exists fuser; then
      if $SUDO fuser "$f" >/dev/null 2>&1; then
        return 0
      fi
    elif [[ -e "$f" ]] && command_exists lsof; then
      if $SUDO lsof "$f" >/dev/null 2>&1; then
        return 0
      fi
    fi
  done
  # Fallback: look for apt/dpkg processes
  if pgrep -x apt-get >/dev/null 2>&1 || pgrep -x apt >/dev/null 2>&1 || pgrep -x dpkg >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

wait_for_apt_lock() {
  local timeout_sec="${1:-180}"
  local start_ts now elapsed
  start_ts="$(date +%s)"
  if ! apt_has_lock; then
    return 0
  fi
  stage "6.3a" "WAIT" "Waiting for apt/dpkg lock (another package manager is busy)"
  while apt_has_lock; do
    now="$(date +%s)"
    elapsed=$((now - start_ts))
    if (( elapsed >= timeout_sec )); then
      stage "6.3a" "FAIL" "apt/dpkg lock held >${timeout_sec}s"
      die "apt/dpkg is locked by another process for over ${timeout_sec}s. Close Ubuntu Software / unattended-upgrades, or reboot WSL (wsl --shutdown), then rerun. Log: $INSTALL_LOG"
    fi
    printf '[AGG::HEARTBEAT] waiting for apt/dpkg lock — elapsed %ss\n' "$elapsed"
    sleep 5
  done
  stage "6.3a" "PASS" "apt/dpkg lock clear"
}

die_with_log_tail() {
  local msg="$1"
  local logf="${2:-$INSTALL_LOG}"
  local lines="${3:-40}"
  local rc="${4:-1}"
  printf '\033[1;31m[AGG::FAIL]\033[0m %s\n' "$msg" >&2
  if [[ -n "$logf" && -f "$logf" ]]; then
    printf '\033[1;31m[AGG::FAIL]\033[0m ---- last %s lines of %s ----\n' "$lines" "$logf" >&2
    tail -n "$lines" "$logf" >&2 || true
    printf '\033[1;31m[AGG::FAIL]\033[0m ---- end log tail ----\n' >&2
  fi
  printf '\033[1;31m[AGG::FAIL]\033[0m Failed stage near line %s. Full log: %s\n' "${BASH_LINENO[0]:-$LINENO}" "$INSTALL_LOG" >&2
  emit_phase_exit "$rc" "die_with_log_tail"
  exit "$rc"
}

# Best-effort primary broken package name for structured failure UI.
dpkg_primary_broken_package() {
  local pkg=""
  # Query the human-readable Status field, not Status-Abbrev: a
  # reinst-required package's abbrev is 3 characters (e.g. "iHR"), which the
  # old 2-char-anchored regex here never matched -- it silently fell through
  # to the generic "(see dpkg --audit / half-state lines above)" text even
  # though dpkg_check_status_anomalies, querying the same Status field
  # directly, had already identified the package correctly. This reuses that
  # proven-correct query instead of a second, narrower one.
  if command_exists dpkg-query; then
    pkg="$($SUDO dpkg-query -W -f='${Status}\t${Package}\n' 2>/dev/null \
      | awk -F'\t' '$1 ~ /half-installed|half-configured|unpacked|reinstreq/ { print $2; exit }' || true)"
  fi
  if [[ -z "$pkg" ]]; then
    # dpkg --audit's real format is a leading space, then "name[:arch]",
    # then a space and a free-text description on the same line -- not a
    # bare package name alone on its own line. Match that shape and strip
    # any :arch suffix.
    pkg="$($SUDO dpkg --audit 2>&1 \
      | grep -E '^ [a-zA-Z0-9][a-zA-Z0-9.+-]*(:[a-zA-Z0-9]+)? ' \
      | head -1 | awk '{print $1}' | cut -d: -f1 || true)"
  fi
  printf '%s\n' "${pkg:-}"
}

# Packages dpkg has explicitly flagged as needing reinstallation -- a
# distinct, narrower condition than half-installed/half-configured/unpacked.
# dpkg --configure -a deliberately skips these by design (reconfiguring
# alone cannot fix a package dpkg considers reinstall-required), which is
# why plain configure+fix-broken passes can legitimately report success
# (0 upgraded, 0 newly installed, 0 to remove) while this class of package
# stays broken. The fix is an explicit reinstall, not more configure passes.
dpkg_reinstreq_packages() {
  if ! command_exists dpkg-query; then
    return 0
  fi
  $SUDO dpkg-query -W -f='${Status}\t${Package}\n' 2>/dev/null \
    | awk -F'\t' '$1 ~ /reinstreq/ { print $2 }'
}

# Explicitly reinstall any reinst-required package(s). Returns 1 (nothing to
# do) when none exist, so callers can skip straight to the normal
# configure/fix-broken path without wasting a step.
dpkg_reinstall_reinstreq() {
  local repair_log="$1"
  local pkgs
  pkgs="$(dpkg_reinstreq_packages)"
  if [[ -z "$pkgs" ]]; then
    return 1
  fi
  log "dpkg reports reinstall-required package(s): $(printf '%s' "$pkgs" | tr '\n' ' ') -- dpkg --configure -a cannot fix this by design; reinstalling explicitly"
  local rc=0
  set +e
  # shellcheck disable=SC2086
  run_watched 300 "apt-get install --reinstall" --soft -- bash -c '
    set -o pipefail
    logf="$1"; shift
    "$@" 2>&1 | tee -a "$logf"
    exit "${PIPESTATUS[0]}"
  ' bash "$repair_log" $SUDO env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a \
    apt-get install --reinstall -y $pkgs
  rc=$?
  set -e
  return "$rc"
}

# ------------------------------------------------------------------------------
# Decomposed dpkg/apt health checks. Each dpkg_check_* function prints exactly
# one PASS/FAIL line plus, on FAIL, the exact command and exact output that
# produced the verdict -- never a summary judgment with nothing to inspect.
#
# Canonical (gating) checks: audit, apt-get check, updates-dir *numeric
# fragments only*, half-installed/half-configured/unpacked states, status
# anomalies, pending triggers, lock state.
#
# dpkg --verify is intentionally NOT a gate: it reports checksum drift for
# any admin-edited config file or locally-modified file, which is normal on
# a real system and unrelated to an interrupted package transaction. It is
# still run and logged for visibility, matching "dpkg --verify if used".
# ------------------------------------------------------------------------------

dpkg_check_audit() {
  local out
  out="$($SUDO dpkg --audit 2>&1)"
  if [[ -n "$out" ]]; then
    log "FAIL  dpkg --audit"
    log "  cmd: dpkg --audit"
    log "  out: $out"
    return 1
  fi
  log "PASS  dpkg --audit (no inconsistent packages)"
  return 0
}

dpkg_check_verify() {
  # Advisory only -- never gates PASS/FAIL. Logged for the requested
  # decomposition ("dpkg --verify if used").
  local out
  out="$($SUDO dpkg --verify 2>&1 || true)"
  if [[ -n "$out" ]]; then
    log "INFO  dpkg --verify (advisory, not a gate) -- checksum drift present, commonly normal:"
    log "  cmd: dpkg --verify"
    log "  out: $out"
  else
    log "INFO  dpkg --verify: no checksum drift"
  fi
  return 0
}

dpkg_check_apt_get_check() {
  local out rc=0
  out="$($SUDO env DEBIAN_FRONTEND=noninteractive apt-get check 2>&1)" || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    log "FAIL  apt-get check (exit=$rc)"
    log "  cmd: apt-get check"
    log "  out: $out"
    return 1
  fi
  log "PASS  apt-get check"
  return 0
}

dpkg_check_updates_dir() {
  # A real interrupted dpkg transaction leaves numbered fragment files
  # (dpkg's own naming convention: pure decimal integers, e.g. "1", "42")
  # directly under /var/lib/dpkg/updates. Any OTHER file in that directory
  # is not evidence of an interrupted transaction and must not fail this
  # check on its own -- that was the exact false-positive reported.
  local updates_dir="/var/lib/dpkg/updates"
  local listing="" f base
  local -a fragments=()
  local -a stale=()
  if [[ -d "$updates_dir" ]]; then
    listing="$($SUDO find "$updates_dir" -mindepth 1 -maxdepth 1 2>/dev/null)"
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      base="$(basename "$f")"
      if [[ "$base" =~ ^[0-9]+$ ]]; then
        fragments+=("$f")
      else
        stale+=("$f")
      fi
    done <<< "$listing"
  fi
  log "cmd: find $updates_dir -mindepth 1 -maxdepth 1"
  log "out: ${listing:-<empty>}"
  if [[ "${#fragments[@]}" -gt 0 ]]; then
    log "FAIL  /var/lib/dpkg/updates has active numbered fragments: ${fragments[*]}"
    return 1
  fi
  if [[ "${#stale[@]}" -gt 0 ]]; then
    log "PASS  /var/lib/dpkg/updates (non-numeric file(s) present, not a pending-transaction signal): ${stale[*]}"
  else
    log "PASS  /var/lib/dpkg/updates has no active fragments"
  fi
  return 0
}

dpkg_check_half_states() {
  local out=""
  if command_exists dpkg-query; then
    out="$($SUDO dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 2>/dev/null | grep -E '^[a-zA-Z]?[UFH]' || true)"
  fi
  if [[ -n "$out" ]]; then
    log "FAIL  half-installed/half-configured/unpacked packages"
    log '  cmd: dpkg-query -W -f="${db:Status-Abbrev} ${Package}\n"'
    log "  out: $out"
    return 1
  fi
  log "PASS  no half-installed/half-configured/unpacked packages"
  return 0
}

dpkg_check_status_anomalies() {
  # Only flag genuinely broken Status values. "deinstall ok config-files" (and
  # similar residual entries) are normal after apt remove and must NOT fail
  # the health gate — that would produce a permanent false "still broken".
  local out=""
  if command_exists dpkg-query; then
    out="$($SUDO dpkg-query -W -f='${Status}\t${Package}\n' 2>/dev/null \
      | awk -F'\t' '
          $1 ~ /half-installed|half-configured|unpacked/ { print; next }
          $1 ~ /reinstreq/ { print; next }
        ' || true)"
  fi
  if [[ -n "$out" ]]; then
    log "FAIL  dpkg-query status anomalies"
    log '  cmd: dpkg-query Status filter for half-installed/half-configured/unpacked/reinst-required'
    log "  out: $out"
    return 1
  fi
  log "PASS  no dpkg-query status anomalies"
  return 0
}

dpkg_check_pending_triggers() {
  local out=""
  if command_exists dpkg-query; then
    out="$($SUDO dpkg-query -W -f='${Triggers-Pending}\t${Package}\n' 2>/dev/null | awk -F'\t' '$1!=""' || true)"
  fi
  if [[ -n "$out" ]]; then
    log "FAIL  packages with pending triggers"
    log '  cmd: dpkg-query -W -f="${Triggers-Pending}\t${Package}\n"'
    log "  out: $out"
    return 1
  fi
  log "PASS  no pending triggers"
  return 0
}

dpkg_check_lock_state() {
  # A lock FILE existing is normal; only a lock actually HELD by a live
  # process means dpkg/apt is genuinely busy elsewhere.
  if command_exists fuser; then
    if $SUDO fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || $SUDO fuser /var/lib/dpkg/lock >/dev/null 2>&1; then
      log "FAIL  dpkg/apt lock held by another process"
      log "  cmd: fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock"
      return 1
    fi
    log "PASS  dpkg/apt lock is free"
  else
    log "PASS  dpkg/apt lock check skipped (fuser not available)"
  fi
  return 0
}

# Runs all 8 requested checks, logs each individually, and returns the
# canonical (gating) verdict. dpkg --verify is run and logged but never
# contributes to the return code -- see comment above dpkg_check_verify.
dpkg_health_report() {
  local overall=0
  dpkg_check_audit || overall=1
  dpkg_check_verify
  dpkg_check_apt_get_check || overall=1
  dpkg_check_updates_dir || overall=1
  dpkg_check_half_states || overall=1
  dpkg_check_status_anomalies || overall=1
  dpkg_check_pending_triggers || overall=1
  dpkg_check_lock_state || overall=1
  return "$overall"
}

# True when dpkg/apt is in the common WSL "interrupted" / half-configured
# state. Thin wrapper over dpkg_health_report kept for callers that only need
# a boolean (e.g. deciding whether apt-get -f install is worth running at
# all); callers that need to explain a failure should call
# dpkg_health_report directly so each check's exact output is logged.
dpkg_needs_repair() {
  ! dpkg_health_report >/dev/null 2>&1
}

# Self-heal interrupted dpkg before apt update/install (one-click; no manual dpkg --configure -a).
repair_interrupted_dpkg() {
  local force="${1:-0}"
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE="${NEEDRESTART_MODE:-a}"
  export APT_LISTCHANGES_FRONTEND=none

  if [[ "$force" != "1" ]] && dpkg_health_report; then
    stage "6.3r" "PASS" "dpkg/apt package state is clean"
    return 0
  fi

  stage "6.3r" "START" "Repairing interrupted dpkg/apt state"
  log "Interrupted package state detected — running dpkg --configure -a (noninteractive)"
  wait_for_apt_lock 180

  local repair_log
  repair_log="${INSTALL_LOG_DIR}/dpkg-repair-$(date +%Y%m%d-%H%M%S).log"
  mkdir -p "$INSTALL_LOG_DIR"

  local attempt
  for attempt in 1 2; do
    local cfg_rc=0
    set +e
    run_watched 600 "dpkg --configure -a" --soft -- bash -c '
      set -o pipefail
      logf="$1"; shift
      "$@" 2>&1 | tee -a "$logf"
      exit "${PIPESTATUS[0]}"
    ' bash "$repair_log" $SUDO env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a dpkg --configure -a
    cfg_rc=$?
    set -e
    if [[ "$cfg_rc" -ne 0 ]]; then
      stage "6.3r" "FAIL" "dpkg --configure -a exit=$cfg_rc"
      local pkg
      pkg="$(dpkg_primary_broken_package || true)"
      if [[ -n "$pkg" ]]; then
        printf 'PACKAGE REPAIR FAILED\nPackage:\n%s\n' "$pkg" | tee -a "$repair_log"
        printf 'dpkg: error processing package %s (--configure)\n' "$pkg" | tee -a "$repair_log"
      fi
      die_with_log_tail \
        "dpkg --configure -a failed with exit $cfg_rc while repairing interrupted package state${pkg:+ (package: $pkg)}. Fix the dpkg error below, then rerun Setup (no manual steps expected for the common WSL interrupt case)." \
        "$repair_log" 80 43
    fi

    if dpkg_reinstall_reinstreq "$repair_log"; then
      stage "6.3r" "INFO" "reinstalled reinstreq package(s) (attempt $attempt/2)"
    fi

    stage "6.3r" "INFO" "apt-get -f install -y (attempt $attempt/2)"
    log "Running apt-get -f install -y to finish dependency repair"
    local fix_rc=0
    set +e
    run_watched 600 "apt-get -f install" --soft -- bash -c '
      set -o pipefail
      logf="$1"; shift
      "$@" 2>&1 | tee -a "$logf"
      exit "${PIPESTATUS[0]}"
    ' bash "$repair_log" $SUDO env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a \
      apt-get \
      -o Acquire::Retries=3 \
      -o Acquire::http::Timeout=30 \
      -o Acquire::https::Timeout=30 \
      -o Dpkg::Use-Pty=0 \
      -o Dpkg::Options::=--force-confdef \
      -o Dpkg::Options::=--force-confold \
      -f install -y
    fix_rc=$?
    set -e
    if [[ "$fix_rc" -ne 0 ]]; then
      stage "6.3r" "FAIL" "apt-get -f install exit=$fix_rc"
      local pkg
      pkg="$(dpkg_primary_broken_package || true)"
      if [[ -n "$pkg" ]]; then
        printf 'PACKAGE REPAIR FAILED\nPackage:\n%s\n' "$pkg" | tee -a "$repair_log"
        printf 'dpkg: error processing package %s (--configure)\n' "$pkg" | tee -a "$repair_log"
      fi
      die_with_log_tail \
        "apt-get -f install -y failed with exit $fix_rc after dpkg --configure -a${pkg:+ (package: $pkg)}. Exact repair log tail follows." \
        "$repair_log" 80 43
    fi

    stage "6.3r" "INFO" "post-repair health check (attempt $attempt/2)"
    log "Post-repair health check (attempt $attempt/2) — each check logged individually:"
    if dpkg_health_report; then
      stage "6.3r" "PASS" "dpkg/apt package state repaired"
      ok "Interrupted dpkg state repaired automatically"
      return 0
    fi

    # Exactly one bounded extra recovery pass, gated only on a genuine
    # canonical-check failure above -- not a broad heuristic retry loop.
    if [[ "$attempt" -eq 1 ]]; then
      warn "A canonical check still failed after the first repair pass — retrying dpkg --configure -a + apt-get -f install once more"
    fi
  done

  local pkg
  pkg="$(dpkg_primary_broken_package || true)"
  [[ -n "$pkg" ]] || pkg="(see dpkg --audit / half-state lines above)"
  printf 'PACKAGE REPAIR FAILED\n' | tee -a "$repair_log"
  printf 'Package:\n%s\n' "$pkg" | tee -a "$repair_log"
  printf 'Problem:\nAutomatic repair finished (configure + apt -f exited 0) but a canonical health check still fails.\n' | tee -a "$repair_log"
  printf 'Repair attempted:\ndpkg --configure -a; apt-get -f install -y (up to 2 passes)\n' | tee -a "$repair_log"
  printf 'Result:\npackage state still broken after repair\n' | tee -a "$repair_log"
  if [[ "$pkg" != "(see dpkg --audit / half-state lines above)" ]]; then
    printf 'dpkg: error processing package %s (--configure)\n' "$pkg" | tee -a "$repair_log"
  fi
  stage "6.3r" "FAIL" "PACKAGE REPAIR FAILED pkg=$pkg"
  die_with_log_tail \
    "dpkg/apt still reports an interrupted or broken package state after two automatic repair passes (package: $pkg). The exact failing check and its exact output were logged above this point. Exact repair log tail follows." \
    "$repair_log" 80 43
}

run_apt() {
  # Bounded, noninteractive apt with heartbeats. Never waits on a TTY prompt.
  # Usage: run_apt TIMEOUT LABEL [--soft] apt-get-args...
  local timeout_sec="$1"; shift
  local label="$1"; shift
  local soft=0
  if [[ "${1:-}" == "--soft" ]]; then soft=1; shift; fi
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE="${NEEDRESTART_MODE:-a}"
  export APT_LISTCHANGES_FRONTEND=none
  wait_for_apt_lock 180
  local soft_flag=()
  if [[ "$soft" -eq 1 ]]; then soft_flag=(--soft); fi
  # shellcheck disable=SC2086
  run_watched "$timeout_sec" "$label" "${soft_flag[@]}" -- $SUDO env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a \
    apt-get \
    -o Acquire::Retries=3 \
    -o Acquire::http::Timeout=30 \
    -o Acquire::https::Timeout=30 \
    -o Acquire::ftp::Timeout=30 \
    -o Dpkg::Use-Pty=0 \
    -o Dpkg::Options::=--force-confdef \
    -o Dpkg::Options::=--force-confold \
    "$@"
}

trap 'printf "\n\033[1;31m[AGG::FAIL]\033[0m Installer stopped on line %s. Log: %s\n" "$LINENO" "$INSTALL_LOG" >&2' ERR
log "Install log → $INSTALL_LOG"

case "${INSTALL_PHASE,,}" in
  auto|privileged|user|finalize) INSTALL_PHASE="${INSTALL_PHASE,,}" ;;
  *) die "Invalid OTACON_INSTALL_PHASE='$INSTALL_PHASE' (use auto|privileged|user|finalize)" ;;
esac
log "Install phase: $INSTALL_PHASE"

printf '\033[1;35m'
cat <<'OTACON_ASCII'
  ___ _____  _    ____ ___  _   _
 / _ \_   _|/ \  / ___/ _ \| \ | |
| | | || | / _ \| |  | | | |  \| |
| |_| || |/ ___ \ |__| |_| | |\  |
 \___/ |_/_/   \_\____\___/|_| \_|

    _    ___   _____ ____ ___  ______   ______ _____ _____ __  __
   / \  |_ _| | ____/ ___/ _ \/ ___\ \ / / ___|_   _| ____|  \/  |
  / _ \  | |  |  _|| |  | | | \___ \\ V /\___ \ | | |  _| | |\/| |
 / ___ \ | |  | |__| |__| |_| |___) || |  ___) || | | |___| |  | |
/_/   \_\___| |_____\____\___/|____/ |_| |____/ |_| |_____|_|  |_|

==============================================================================
                        O T A C O N S K E E P
                     AUTOMATED PUBLIC INSTALLER
==============================================================================
                         ANTONIO G. GARCIA
                         Built for the Keep.
==============================================================================
OTACON_ASCII
printf '\033[0m\n'
printf '\033[1;36m%s\033[0m\n' "$BRAND"
printf '\033[0;37m%s :: %s\033[0m\n' "$PRODUCT" "$TAGLINE"
printf '\033[0;37mThis is Otacon Core -- free, full source, no license key, no time limit.\033[0m\n'
printf '\033[0;37mOtaconskeep Services (architecture, deployment, support) -- come say hi: %s\033[0m\n\n' "$DISCORD_URL"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

is_debian_family() {
  [[ -f /etc/os-release ]] || return 1
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" || "${ID_LIKE:-}" == *"debian"* ]]
}

classify_os_support() {
  # Sets OS_SUPPORT to supported | best_effort | unsupported
  [[ -f /etc/os-release ]] || { OS_SUPPORT=unsupported; return; }
  # shellcheck disable=SC1091
  . /etc/os-release
  local id="${ID:-}" ver="${VERSION_ID:-}" like="${ID_LIKE:-}"
  OS_SUPPORT=unsupported
  case "$id" in
    ubuntu)
      case "$ver" in
        22.04|24.04) OS_SUPPORT=supported ;;
        20.04|18.04) OS_SUPPORT=unsupported ;;
        *) OS_SUPPORT=best_effort ;;
      esac
      ;;
    debian)
      case "$ver" in
        12|12.*) OS_SUPPORT=supported ;;
        11|11.*) OS_SUPPORT=unsupported ;;
        *) OS_SUPPORT=best_effort ;;
      esac
      ;;
    linuxmint|pop|elementary|zorin)
      OS_SUPPORT=best_effort
      ;;
    *)
      if [[ "$like" == *"debian"* || "$like" == *"ubuntu"* ]]; then
        OS_SUPPORT=best_effort
      else
        OS_SUPPORT=unsupported
      fi
      ;;
  esac
}

is_debian_family || die \
  "This terminal isn't running Ubuntu or Debian Linux, which is what this installer needs. What to do: on Windows, this means you're in PowerShell, CMD, or Git Bash -- none of those work. Open an elevated PowerShell, run 'wsl --install' (installs WSL2 + Ubuntu, one reboot required), then open the new Ubuntu app from your Start menu and run this same command again inside THAT window. On a Mac, you'll need an Ubuntu VM (UTM, Parallels, VMware) or a real Linux box; native macOS support isn't here yet. Ask in Discord ($DISCORD_URL) if you get stuck."

classify_os_support
log "OS support class: $OS_SUPPORT ($(. /etc/os-release; echo "${PRETTY_NAME:-unknown}"))"
case "$OS_SUPPORT" in
  supported) ok "Supported platform" ;;
  best_effort)
    warn "Best-effort platform — Core web install is attempted; native desktop (Tauri) may fail."
    if [[ "$BUILD_NATIVE" == "1" ]]; then
      warn "Consider OTACON_PROFILE=core (default) to skip native .deb on best-effort distros."
    fi
    ;;
  unsupported)
    if [[ "$ALLOW_UNSUPPORTED_OS" == "1" ]]; then
      warn "Unsupported OS — continuing because OTACON_ALLOW_UNSUPPORTED_OS=1"
    else
      die "This OS version is unsupported for Otacon. Supported: Ubuntu 22.04/24.04, Debian 12. Set OTACON_ALLOW_UNSUPPORTED_OS=1 to override (Core web-only may still work)."
    fi
    ;;
esac

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  if [[ "$INSTALL_PHASE" == "auto" ]]; then
    warn "Running the full installer as root is not recommended for auto mode."
    warn "Prefer: privileged phase as root, then user phase as the normal account."
  fi
fi

# Elevation model:
#   - Windows one-click: privileged/finalize via `wsl -u root` (no sudoers change)
#   - user phase: never calls apt/sudo
#   - auto (interactive Linux TTY): may use sudo with a password prompt
# Permanent NOPASSWD:ALL is NOT required and NOT configured by this installer.
SUDO=""
NEED_PRIVILEGED_HELPER=0
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  SUDO=""
elif [[ "$INSTALL_PHASE" == "user" ]]; then
  SUDO=""
  NEED_PRIVILEGED_HELPER=0
elif [[ "$INSTALL_PHASE" == "privileged" || "$INSTALL_PHASE" == "finalize" ]]; then
  die "OTACON_INSTALL_PHASE=$INSTALL_PHASE must run as root (Windows: wsl.exe -u root). Do not use sudo NOPASSWD:ALL."
elif command_exists sudo; then
  if [[ -t 0 ]] && [[ -t 1 ]]; then
    SUDO="sudo"
    ok "Interactive TTY detected — sudo may ask for your password for system packages only"
  elif sudo -n true >/dev/null 2>&1; then
    SUDO="sudo -n"
    ok "Existing passwordless sudo detected (not created by Otacon); using sudo -n"
  else
    NEED_PRIVILEGED_HELPER=1
    warn "No TTY and no passwordless sudo — system package steps must be done via root phase (wsl -u root)."
  fi
else
  die "This installer needs root for a few system packages, and 'sudo' isn't available. What to do: install sudo or rerun the privileged phase as root."
fi

resolve_target_user() {
  if [[ -n "$TARGET_USER" ]]; then
    printf '%s\n' "$TARGET_USER"
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    # Prefer the default WSL user from /etc/wsl.conf or the first non-system user with a home.
    if [[ -f /etc/wsl.conf ]]; then
      local conf_user
      conf_user="$(awk -F= '/^[[:space:]]*default=/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' /etc/wsl.conf 2>/dev/null || true)"
      if [[ -n "$conf_user" ]] && id "$conf_user" >/dev/null 2>&1; then
        printf '%s\n' "$conf_user"
        return 0
      fi
    fi
    local cand
    cand="$(getent passwd | awk -F: '$3>=1000 && $3!=65534 && $1!="root" && $6!="" && $6!="/" && $6!="/nonexistent" && $7!="" && $7!="/usr/sbin/nologin" && $7!="/sbin/nologin" && $7!="/bin/false" {print $1; exit}')"
    if [[ -n "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
    die "Could not determine OTACON_TARGET_USER while running as root. Set OTACON_TARGET_USER explicitly."
  fi
  id -un
}

# ------------------------------------------------------------------------------
# WSL: make sure systemd is active before doing anything else. Enabling it
# only takes effect on the *next* boot of this WSL distro (not a Windows
# reboot -- just this Linux environment restarting), so if we just turned it
# on, stop here with a distinct exit code. The Windows-side installer
# (install_otacon.bat) restarts WSL and reruns this script automatically;
# every step below is safe to redo, so the rerun just picks up from here.
# ------------------------------------------------------------------------------

ensure_wsl_systemd() {
  if ! grep -qi microsoft /proc/version 2>/dev/null; then
    return 0
  fi
  local WSL_CONF="/etc/wsl.conf"
  if grep -qE '^\s*systemd\s*=\s*true' "$WSL_CONF" 2>/dev/null; then
    return 0
  fi
  log "Enabling systemd in WSL (needed so Otacon can auto-start with Windows)"
  if [[ "${EUID:-$(id -u)}" -ne 0 && -z "$SUDO" ]]; then
    die "Need root to edit /etc/wsl.conf. Windows Setup should run the privileged phase as wsl -u root."
  fi
  if [[ -f "$WSL_CONF" ]] && grep -q '^\[boot\]' "$WSL_CONF"; then
    $SUDO sed -i '/^\[boot\]/a systemd=true' "$WSL_CONF"
  else
    printf '[boot]\nsystemd=true\n' | $SUDO tee -a "$WSL_CONF" >/dev/null
  fi
  warn "This Linux environment needs to restart once to activate that. If you're seeing this from install_otacon.bat, it will handle the restart and continue automatically."
  emit_phase_exit 42 "wsl-systemd-restart-required"
  exit 42
}

install_apt_packages() {
  stage "6.3" "START" "Installing Linux build dependencies via apt"
  log "Checking Linux build dependencies"
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a
  export APT_LISTCHANGES_FRONTEND=none

  local APT_PACKAGES=(
    ca-certificates curl file git build-essential pkg-config
    python3 python3-venv python3-pip libssl-dev zstd
  )
  if [[ "$BUILD_NATIVE" == "1" ]]; then
    APT_PACKAGES+=(
      libwebkit2gtk-4.1-dev
      libayatana-appindicator3-dev
      librsvg2-dev
      libxdo-dev
    )
  fi
  printf '[AGG::PROGRESS] apt packages (%s): %s\n' "${#APT_PACKAGES[@]}" "${APT_PACKAGES[*]}"

  # Common WSL failure: prior apt killed mid-configure → "dpkg was interrupted".
  # Self-heal before update/install so one-click Setup does not ask the user to
  # manually run dpkg --configure -a.
  repair_interrupted_dpkg

  local apt_rc=0
  set +e
  run_apt 600 "apt-get update" --soft update -y
  apt_rc=$?
  set -e
  if [[ "$apt_rc" -ne 0 ]]; then
    if dpkg_needs_repair; then
      warn "apt-get update failed (exit $apt_rc) with interrupted dpkg — repairing and retrying once"
      repair_interrupted_dpkg 1
      run_apt 600 "apt-get update (retry after dpkg repair)" update -y
    else
      die_with_log_tail "apt-get update failed with exit $apt_rc (not an interrupted-dpkg case). Log tail follows." "$INSTALL_LOG" 50
    fi
  fi

  set +e
  run_apt 1200 "apt-get install build dependencies" --soft install -y "${APT_PACKAGES[@]}"
  apt_rc=$?
  set -e
  if [[ "$apt_rc" -ne 0 ]]; then
    if dpkg_needs_repair || [[ "$apt_rc" -eq 100 ]]; then
      warn "apt-get install failed (exit $apt_rc) — attempting dpkg repair + one retry"
      repair_interrupted_dpkg 1
      set +e
      run_apt 1200 "apt-get install build dependencies (retry)" --soft install -y "${APT_PACKAGES[@]}"
      apt_rc=$?
      set -e
    fi
    if [[ "$apt_rc" -ne 0 ]]; then
      stage "6.3" "FAIL" "apt-get install exit=$apt_rc"
      die_with_log_tail \
        "apt-get install build dependencies failed with exit $apt_rc after automatic dpkg repair. Exact apt/dpkg log tail follows (not a generic exit 100)." \
        "$INSTALL_LOG" 60
    fi
  fi

  stage "6.3" "PASS" "Linux build dependencies installed"
  ok "System dependencies are installed"
}

phase_privileged() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "privileged phase requires root (wsl.exe -u root)"
  TARGET_USER="$(resolve_target_user)"
  id "$TARGET_USER" >/dev/null 2>&1 || die "OTACON_TARGET_USER='$TARGET_USER' does not exist"
  stage "6.0" "PASS" "Running privileged bootstrap as root for user=$TARGET_USER"
  ensure_wsl_systemd
  install_apt_packages
  if [[ "$INSTALL_DEFAULT_MODEL" == "1" ]]; then
    stage "6.3b" "START" "Installing Ollama (system)"
    if ! command_exists ollama; then
      run_watched 300 "ollama install script" -- bash -c 'curl -fsSL --connect-timeout 30 --max-time 240 https://ollama.com/install.sh | sh'
    else
      ok "Ollama already installed"
    fi
    if command_exists systemctl && [[ -d /run/systemd/system ]]; then
      systemctl enable ollama >/dev/null 2>&1 || true
      systemctl restart ollama >/dev/null 2>&1 || true
    fi
    stage "6.3b" "PASS" "Ollama present"
  fi

  mkdir -p "$PRIV_MARKER_DIR"
  printf 'user=%s\nts=%s\n' "$TARGET_USER" "$(date -Iseconds)" > "$PRIV_MARKER"
  chmod 644 "$PRIV_MARKER"

  # Voice Trainer needs apt/docker — must run as root on Windows (no NOPASSWD:ALL).
  # Running it in the user phase hangs forever on `sudo` password with no TTY.
  if [[ "$INSTALL_VOICE_TRAINER" == "1" ]]; then
    # Same WSL PATH trap as Expansion: prefer absolute nvidia-smi under /usr/lib/wsl/lib.
    _vt_smi=""
    if command_exists nvidia-smi; then _vt_smi="$(command -v nvidia-smi)"
    elif [[ -x /usr/lib/wsl/lib/nvidia-smi ]]; then _vt_smi=/usr/lib/wsl/lib/nvidia-smi
    elif [[ -x /usr/bin/nvidia-smi ]]; then _vt_smi=/usr/bin/nvidia-smi
    fi
    if [[ -n "$_vt_smi" ]] && PATH="/usr/lib/wsl/lib:${PATH:-}" LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$_vt_smi" >/dev/null 2>&1; then
      local user_home vt_dir vt_rc=0
      user_home="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
      [[ -n "$user_home" && -d "$user_home" ]] || die "Cannot resolve home for $TARGET_USER (Voice Trainer)"
      vt_dir="$user_home/otacon-voice-trainer"
      stage "6.3v" "START" "Installing Genome Voice Trainer as root into $vt_dir"
      export OTACON_VT_DIR="$vt_dir"
      export OTACON_VT_SKIP_UI=1
      set +e
      run_watched 3600 "Genome Voice Trainer install" --soft -- bash -c \
        'curl -fsSL --connect-timeout 30 --max-time 120 "$1" | bash' \
        bash "$VOICE_TRAINER_INSTALLER_URL"
      vt_rc=$?
      set -e
      if [[ "$vt_rc" -eq 0 ]]; then
        chown -R "$TARGET_USER":"$TARGET_USER" "$vt_dir" 2>/dev/null || true
        usermod -aG docker "$TARGET_USER" 2>/dev/null || true
        printf 'voice_trainer=ok\n' >>"$PRIV_MARKER"
        stage "6.3v" "PASS" "Genome Voice Trainer installed for $TARGET_USER"
        ok "Genome Voice Trainer installed (privileged phase; no sudo password hang)"
      else
        printf 'voice_trainer=fail rc=%s\n' "$vt_rc" >>"$PRIV_MARKER"
        stage "6.3v" "FAIL" "Voice Trainer exit=$vt_rc (optional)"
        warn "Genome Voice Trainer failed in privileged phase (exit $vt_rc) — Otacon Core continues; retry later as root."
      fi
    else
      printf 'voice_trainer=skipped no-gpu\n' >>"$PRIV_MARKER"
      stage "6.3v" "INFO" "Voice Trainer skipped — no usable NVIDIA GPU"
      warn "Voice Trainer skipped in privileged phase — nvidia-smi not usable (try Fix-Otacon-GPU.bat on WSL)"
    fi
  fi

  stage "6.0" "PASS" "Privileged bootstrap complete"
  ok "Privileged bootstrap complete (no sudoers changes were made)"
  emit_phase_exit 0 "privileged-ok"
  exit 0
}

phase_finalize() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "finalize phase requires root (wsl.exe -u root)"
  TARGET_USER="$(resolve_target_user)"
  local user_home service_draft service_file tts_draft tts_file
  user_home="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
  [[ -n "$user_home" && -d "$user_home" ]] || die "Cannot resolve home for $TARGET_USER"
  service_draft="$user_home/.config/otacon/$SERVICE_DRAFT_NAME"
  service_file="/etc/systemd/system/otacon.service"
  tts_draft="$user_home/.config/otacon/otacon-tts.service.draft"
  tts_file="/etc/systemd/system/otacon-tts.service"
  stage "6.7" "START" "Installing systemd unit for user=$TARGET_USER"
  if [[ ! -f "$service_draft" ]]; then
    die "Missing service draft at $service_draft — run the user phase first."
  fi
  # Ownership check: draft must belong to target user (not planted by another account).
  local draft_owner
  draft_owner="$(stat -c '%U' "$service_draft" 2>/dev/null || true)"
  if [[ "$draft_owner" != "$TARGET_USER" ]]; then
    die "Service draft owner is '$draft_owner', expected '$TARGET_USER'. Aborting finalize."
  fi
  install -m 644 "$service_draft" "$service_file"

  # P0-1 / P0-5: Piper was installed in user phase ⇒ TTS unit is required for finalize PASS.
  local piper_expected=0
  if [[ -f "$tts_draft" ]] || [[ -d "$user_home/.config/otacon/piper" ]] || \
     [[ -f "$user_home/.config/otacon/tts.env" ]]; then
    piper_expected=1
  fi
  if [[ -f "$tts_draft" ]]; then
    local tts_owner
    tts_owner="$(stat -c '%U' "$tts_draft" 2>/dev/null || true)"
    if [[ "$tts_owner" == "$TARGET_USER" ]]; then
      install -m 644 "$tts_draft" "$tts_file"
      ok "Installed otacon-tts.service from user draft"
    else
      die "otacon-tts.service.draft owner is '$tts_owner', expected '$TARGET_USER'"
    fi
  elif [[ "$piper_expected" == "1" ]]; then
    die "Piper data present but otacon-tts.service.draft missing — re-run user phase 6.5t"
  else
    warn "No otacon-tts.service.draft — voice preview not configured this install"
  fi

  if command_exists systemctl && [[ -d /run/systemd/system ]]; then
    # Kill orphan nohup Piper so the unit owns :10200
    pkill -f "wyoming-piper.*10200" 2>/dev/null || true
    sleep 1
    systemctl daemon-reload
    if [[ -f "$tts_file" ]]; then
      systemctl enable otacon-tts.service >/dev/null 2>&1 || true
      systemctl restart otacon-tts.service || true
      sleep 2
      if ! systemctl is-active --quiet otacon-tts.service; then
        die "otacon-tts.service failed to become active after finalize (journalctl -u otacon-tts)"
      fi
      ok "otacon-tts.service enabled and active"
    elif [[ "$piper_expected" == "1" ]]; then
      die "Piper expected but otacon-tts.service was not installed"
    fi
    systemctl enable otacon.service >/dev/null 2>&1 || true
    systemctl restart otacon.service
    if ! systemctl is-enabled --quiet otacon.service 2>/dev/null; then
      warn "otacon.service enable returned non-zero — check systemd"
    fi
    if command_exists ollama; then
      systemctl enable ollama >/dev/null 2>&1 || true
      systemctl restart ollama >/dev/null 2>&1 || true
    fi
    ok "otacon.service installed and started as user=$TARGET_USER"
  else
    warn "systemd not active yet; unit installed to $service_file for next boot"
    if [[ "$piper_expected" == "1" && ! -f "$tts_file" ]]; then
      die "systemd inactive and TTS unit missing — cannot guarantee durable voice"
    fi
  fi
  stage "6.7" "PASS" "Finalize complete"
  emit_phase_exit 0 "finalize-ok"
  exit 0
}

if [[ "$INSTALL_PHASE" == "privileged" ]]; then
  phase_privileged
fi
if [[ "$INSTALL_PHASE" == "finalize" ]]; then
  phase_finalize
fi

# user / auto continue below
if [[ "$INSTALL_PHASE" == "user" && "${EUID:-$(id -u)}" -eq 0 ]]; then
  die "user phase must not run as root (file ownership would be wrong). Use the default WSL user."
fi

ensure_wsl_systemd

# ------------------------------------------------------------------------------
# Hardware scan
# ------------------------------------------------------------------------------

log "Antonio G. Garcia hardware scan"

OS_PRETTY="$(
  . /etc/os-release
  printf '%s' "${PRETTY_NAME:-Linux}"
)"

CPU_MODEL="$(
  if command_exists lscpu; then
    lscpu | awk -F: '/Model name/{sub(/^[ \t]+/,"",$2); print $2; exit}'
  else
    uname -m
  fi
)"

CPU_CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1)"

RAM_GB="$(
  awk '/MemTotal/{printf "%.1f", $2/1024/1024}' /proc/meminfo
)"

FREE_GB="$(
  df -Pk "$HOME" | awk 'NR==2{printf "%.1f", $4/1024/1024}'
)"

GPU_NAME="None detected"
GPU_VRAM_GB="0"
GPU_STATUS="CPU fallback"

if command_exists nvidia-smi; then
  GPU_LINE="$(
    nvidia-smi \
      --query-gpu=name,memory.total \
      --format=csv,noheader,nounits 2>/dev/null \
      | head -n1 || true
  )"

  if [[ -n "$GPU_LINE" ]]; then
    GPU_NAME="$(printf '%s' "$GPU_LINE" | awk -F, '{gsub(/^[ \t]+|[ \t]+$/,"",$1); print $1}')"
    GPU_VRAM_MB="$(printf '%s' "$GPU_LINE" | awk -F, '{gsub(/^[ \t]+|[ \t]+$/,"",$2); print int($2)}')"
    GPU_VRAM_GB="$(awk -v m="$GPU_VRAM_MB" 'BEGIN{printf "%.1f",m/1024}')"
    GPU_STATUS="NVIDIA detected"
  fi
fi

# Default chat model by NVIDIA VRAM (matches core/models.py):
#   <6 GB or CPU -> qwen2.5:1.5b
#   >=6 GB       -> qwen2.5:3b
#   >=8 GB       -> qwen2.5:7b
#   >=16 GB      -> qwen2.5:14b
RECOMMENDED_MODEL="qwen2.5:1.5b"
MODEL_ID="chat_small"
MODEL_TIER="Conversational Small"

if awk -v v="$GPU_VRAM_GB" 'BEGIN{exit !(v>=16)}'; then
  RECOMMENDED_MODEL="qwen2.5:14b"
  MODEL_ID="chat_large"
  MODEL_TIER="Conversational Large"
elif awk -v v="$GPU_VRAM_GB" 'BEGIN{exit !(v>=8)}'; then
  RECOMMENDED_MODEL="qwen2.5:7b"
  MODEL_ID="chat_standard"
  MODEL_TIER="Conversational Standard"
elif awk -v v="$GPU_VRAM_GB" 'BEGIN{exit !(v>=6)}'; then
  RECOMMENDED_MODEL="qwen2.5:3b"
  MODEL_ID="chat_medium"
  MODEL_TIER="Conversational Medium"
fi

if [[ -n "${OTACON_LLM_MODEL:-}" ]]; then
  RECOMMENDED_MODEL="$OTACON_LLM_MODEL"
  MODEL_TIER="User override"
fi

printf '\n'
printf '  OS          : %s\n' "$OS_PRETTY"
printf '  CPU         : %s\n' "${CPU_MODEL:-Unknown}"
printf '  CPU cores   : %s\n' "$CPU_CORES"
printf '  RAM         : %s GB\n' "$RAM_GB"
printf '  Free storage: %s GB\n' "$FREE_GB"
printf '  GPU         : %s\n' "$GPU_NAME"
printf '  GPU VRAM    : %s GB\n' "$GPU_VRAM_GB"
printf '  GPU state   : %s\n' "$GPU_STATUS"
printf '  Model tier  : %s\n' "$MODEL_TIER"
printf '  Default LLM : %s\n' "$RECOMMENDED_MODEL"
printf '  Install profile : %s (native build=%s)\n' "$OTACON_PROFILE" "$BUILD_NATIVE"
printf '  LAN mode    : %s (bind %s:%s)\n' "$([[ "$LAN_MODE" == "1" ]] && echo enabled || echo local-only)" "$CHAT_HOST" "$CHAT_PORT"
if [[ "$INSTALL_DEFAULT_MODEL" == "1" ]]; then
  printf '  LLM install : yes (Default Model — normal Otacon install)\n'
else
  printf '  LLM install : skipped (OTACON_INSTALL_DEFAULT_MODEL=0)\n'
fi

# Hardware thresholds (PASS / WARNING / FAIL)
log "Preflight resource thresholds"
PREFLIGHT_FAIL=0
ram_check="$(awk -v r="$RAM_GB" 'BEGIN{ if (r+0 < 4) print "FAIL"; else if (r+0 < 8) print "WARNING"; else print "PASS" }')"
disk_check="$(awk -v d="$FREE_GB" 'BEGIN{ if (d+0 < 8) print "FAIL"; else if (d+0 < 20) print "WARNING"; else print "PASS" }')"
printf '  [%-7s] RAM %s GB (min 4 GB, prefer 8+ GB)\n' "$ram_check" "$RAM_GB"
printf '  [%-7s] Free disk %s GB (min 8 GB, prefer 20+ GB for models)\n' "$disk_check" "$FREE_GB"
if [[ "$ram_check" == "FAIL" || "$disk_check" == "FAIL" ]]; then
  PREFLIGHT_FAIL=1
fi
# Port occupancy
if command_exists ss; then
  if ss -ltn 2>/dev/null | awk -v p=":$CHAT_PORT" '$4 ~ p"$"{found=1} END{exit !found}'; then
    warn "Port $CHAT_PORT appears already in use — installer will reuse/restart Otacon service if present."
  else
    ok "Port $CHAT_PORT is free"
  fi
fi
# Download reachability
if curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1; then
  ok "Network reachability: github.com"
else
  warn "Cannot reach github.com — clone/update may fail"
  PREFLIGHT_FAIL=1
fi
if [[ "$PREFLIGHT_FAIL" == "1" ]]; then
  die "Preflight failed (RAM/disk/network). Free resources or fix connectivity, then rerun. Log: $INSTALL_LOG"
fi

# ------------------------------------------------------------------------------
# System packages
# ------------------------------------------------------------------------------

stage "6.2" "START" "GPU visibility check (Windows WSL path)"
if command_exists nvidia-smi && nvidia-smi >/dev/null 2>&1; then
  GPU_PROBE="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 | tr -d '\r' || true)"
  stage "6.2" "PASS" "nvidia-smi OK in Linux: ${GPU_PROBE:-detected}"
  ok "WSL/Linux can see NVIDIA GPU: ${GPU_PROBE:-detected}"
else
  stage "6.2" "INFO" "nvidia-smi not usable in this Linux environment (Core continues; Voice Trainer may skip)"
  warn "nvidia-smi is missing or failed inside this Linux environment."
  warn "Piper TTS runs on CPU and does not need a GPU — spoken voice still works without nvidia-smi."
  warn "Genome Voice Trainer (optional) needs WSL2 GPU. If Windows nvidia-smi shows an RTX card but this does not, update the NVIDIA Windows driver, enable WSL2 GPU, then reopen Ubuntu."
fi

SKIP_APT=0
if [[ "$INSTALL_PHASE" == "user" ]]; then
  SKIP_APT=1
elif [[ -f "$PRIV_MARKER" ]]; then
  SKIP_APT=1
  ok "Privileged bootstrap marker present — skipping apt in user/auto phase"
fi

if [[ "$SKIP_APT" == "1" ]]; then
  stage "6.3" "PASS" "System packages already provided by privileged phase / skip"
  # Sanity: critical tools must exist
  for req in git python3 curl; do
    command_exists "$req" || die "Missing required tool '$req' after privileged bootstrap. Re-run Windows Setup so the root phase can install packages."
  done
else
  if [[ "$NEED_PRIVILEGED_HELPER" == "1" ]]; then
    die "Cannot install system packages without a TTY or root. Windows Setup should run OTACON_INSTALL_PHASE=privileged via wsl.exe -u root first (no NOPASSWD:ALL required)."
  fi
  install_apt_packages
fi

# ------------------------------------------------------------------------------
# Git clone / update
# ------------------------------------------------------------------------------

log "Synchronizing Otacon public repository"
stage "6.4" "START" "Cloning/updating Otacon repository"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  run_watched 300 "git fetch" -- git -C "$INSTALL_DIR" fetch --prune origin
  CURRENT_BRANCH="$(git -C "$INSTALL_DIR" branch --show-current || true)"

  # Always hard-sync public installs to origin/main so GPU/Codec fixes land.
  # ff-only alone left friends stuck on stale trees after local edits/patches.
  if [[ "$CURRENT_BRANCH" == "main" || -z "$CURRENT_BRANCH" ]]; then
    if ! run_watched 300 "git pull ff-only" -- git -C "$INSTALL_DIR" pull --ff-only; then
      warn "Fast-forward pull failed — hard-resetting to origin/main so fixes apply."
      run_watched 300 "git reset hard" -- git -C "$INSTALL_DIR" reset --hard origin/main
    fi
    # Guarantee tip matches GitHub even when ff-only "succeeded" on an old remote.
    run_watched 120 "git reset hard tip" -- git -C "$INSTALL_DIR" reset --hard origin/main
  else
    warn "Repository is on branch '${CURRENT_BRANCH:-detached}'."
    warn "Leaving local branch selection untouched; fetched origin only."
  fi
elif [[ -e "$INSTALL_DIR" ]]; then
  die "$INSTALL_DIR already exists but isn't an Otacon install this script recognizes. What to do: rename or delete that folder (if it's not something you need), or set OTACON_INSTALL_DIR=/some/other/path before rerunning this script to install somewhere else."
else
  run_watched 600 "git clone" -- git clone "$REPO_URL" "$INSTALL_DIR"
fi

stage "6.4" "PASS" "Repository ready"
ok "Repository ready: $INSTALL_DIR"

cd "$INSTALL_DIR"

# ------------------------------------------------------------------------------
# Python
# ------------------------------------------------------------------------------

log "Checking Python compatibility"

PYTHON_BIN="$(command -v python3)"
PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')"

if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 10) )); then
  die "Otacon needs Python 3.10 or newer; this machine has $PY_VER. What to do: run 'sudo apt-get update && sudo apt-get install -y python3.12' (or ask in Discord: $DISCORD_URL), then rerun this script."
fi

ok "Python $PY_VER"

log "Creating/reusing isolated Python environment"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VPY="$VENV_DIR/bin/python"
VPIP="$VENV_DIR/bin/pip"

"$VPY" -m pip install --upgrade pip setuptools wheel

# Source of truth: requirements-core.txt (psutil, pyinstaller, cryptography, …)
REQ_CORE="$INSTALL_DIR/requirements-core.txt"
if [[ -f "$REQ_CORE" ]]; then
  log "Installing Core Python dependencies from requirements-core.txt"
  "$VPIP" install --upgrade -r "$REQ_CORE"
else
  warn "requirements-core.txt missing — falling back to pinned Core packages"
  "$VPIP" install --upgrade psutil pyinstaller cryptography argon2-cffi
fi

# Prove cryptography is importable in the same venv that runs self-tests.
if ! "$VPY" -c "import cryptography; print(cryptography.__version__)"; then
  die "cryptography failed to import in $VENV_DIR — self-tests would fail. Re-run Setup or install cryptography into the Otacon venv."
fi
if ! "$VPY" -c "import argon2; print('argon2-ok')"; then
  die "argon2-cffi failed to import in $VENV_DIR — Expansion crypto self-tests would fail."
fi

# Python 3.13 removed stdlib audioop; the current public source imports it.
if (( PY_MAJOR > 3 || (PY_MAJOR == 3 && PY_MINOR >= 13) )); then
  log "Python $PY_VER detected; installing audioop compatibility package"
  "$VPIP" install --upgrade audioop-lts
fi

if [[ "$INSTALL_STT" == "1" ]]; then
  log "Installing optional Faster-Whisper package"
  "$VPIP" install --upgrade faster-whisper
  log "STT functional gate (package alone is not READY)"
  if PYTHONPATH=. "$VPY" installer/backend_entry.py validate-stt --real; then
    ok "STT real validation passed"
  else
    warn "STT package installed but functional readiness failed — capability will stay unavailable"
    OPTIONAL_FAIL=1
  fi
else
  warn "Faster-Whisper installation skipped (OTACON_INSTALL_STT=0)."
  warn "Installing the package alone never marks STT READY; use OTACON_INSTALL_STT=1 and pass validate-stt --real."
fi

# ------------------------------------------------------------------------------
# Piper TTS (Wyoming) — required for spoken Preview / Auto Speak / message ▶
# ------------------------------------------------------------------------------
write_otacon_tts_unit_draft() {
  local data_dir="${1:?}"
  local port="${2:?}"
  local run_user="${3:-$(id -un)}"
  mkdir -p "$HOME/.config/otacon"
  # Prefer venv entrypoint; fall back to python -m for older venvs.
  local exec_start
  if [[ -x "$VENV_DIR/bin/wyoming-piper" ]]; then
    exec_start="$VENV_DIR/bin/wyoming-piper --voice en_US-lessac-medium --uri tcp://127.0.0.1:${port} --data-dir $data_dir --download-dir $data_dir"
  else
    exec_start="$VPY -m wyoming_piper --voice en_US-lessac-medium --uri tcp://127.0.0.1:${port} --data-dir $data_dir --download-dir $data_dir"
  fi
  cat >"$HOME/.config/otacon/otacon-tts.service.draft" <<TTSEOF
[Unit]
Description=Otacon Piper TTS (Wyoming)
After=network.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$exec_start
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
TTSEOF
}

start_piper_process() {
  local data_dir="${1:?}"
  local port="${2:?}"
  mkdir -p "$HOME/.config/otacon/logs"
  if command_exists systemctl && [[ -d /run/systemd/system ]]; then
    systemctl --user stop otacon-tts.service 2>/dev/null || true
    systemctl stop otacon-tts.service 2>/dev/null || true
  fi
  # Kill any leftover wyoming-piper on this port (old nohup / failed unit).
  pkill -f "wyoming-piper.*${port}" 2>/dev/null || true
  sleep 1
  local piper_cmd=()
  if [[ -x "$VENV_DIR/bin/wyoming-piper" ]]; then
    piper_cmd=("$VENV_DIR/bin/wyoming-piper")
  else
    piper_cmd=("$VPY" -m wyoming_piper)
  fi
  nohup "${piper_cmd[@]}" \
    --voice en_US-lessac-medium \
    --uri "tcp://127.0.0.1:${port}" \
    --data-dir "$data_dir" \
    --download-dir "$data_dir" \
    >"$HOME/.config/otacon/logs/piper-tts.log" 2>&1 &
  echo $! >"$HOME/.config/otacon/piper-tts.pid"
}

piper_health_ok() {
  local endpoint="${1:?}"
  local timeout="${2:-5}"
  PYTHONPATH="$INSTALL_DIR" OTACON_TTS_PROVIDER=piper OTACON_TTS_ENDPOINT="$endpoint" \
    "$VPY" -c "from core.wyoming_transport import wyoming_health; print(wyoming_health('$endpoint', timeout=$timeout))" 2>/dev/null \
    | grep -q TTS_READY
}

ensure_otacon_tts_running() {
  # Prefer systemd unit (durable). Fall back to nohup only if unit absent.
  local data_dir="${OTACON_PIPER_DATA_DIR:-$HOME/.config/otacon/piper}"
  local port="${OTACON_TTS_PORT:-10200}"
  local endpoint="wyoming://127.0.0.1:${port}"
  mkdir -p "$data_dir"
  if [[ -f "$HOME/.config/otacon/tts.env" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$HOME/.config/otacon/tts.env"; set +a
    endpoint="${OTACON_TTS_ENDPOINT:-$endpoint}"
  fi
  if piper_health_ok "$endpoint" 3; then
    return 0
  fi
  warn "Piper TTS not healthy — restarting"
  if command_exists systemctl && [[ -d /run/systemd/system ]] && \
     systemctl list-unit-files otacon-tts.service >/dev/null 2>&1; then
    # Clear orphan nohup so the unit owns the port
    pkill -f "wyoming-piper.*${port}" 2>/dev/null || true
    sleep 1
    systemctl restart otacon-tts.service >/dev/null 2>&1 || systemctl start otacon-tts.service >/dev/null 2>&1 || true
    sleep 3
    if piper_health_ok "$endpoint" 5; then
      ok "Piper TTS restarted via systemd otacon-tts.service"
      return 0
    fi
  fi
  if ! "$VPIP" show wyoming-piper >/dev/null 2>&1 && ! "$VPY" -c "import wyoming_piper" 2>/dev/null; then
    warn "wyoming-piper is not installed in the venv — voice preview will fail until Setup stage 6.5t succeeds"
    return 1
  fi
  # Last resort session-only start (finalize must still promote the unit)
  start_piper_process "$data_dir" "$port"
  sleep 3
  if piper_health_ok "$endpoint" 5; then
    ok "Piper TTS restarted at $endpoint (session nohup — finalize must install systemd unit)"
    return 0
  fi
  sleep 8
  if piper_health_ok "$endpoint" 5; then
    ok "Piper TTS restarted at $endpoint (session nohup — finalize must install systemd unit)"
    return 0
  fi
  warn "Piper TTS still unhealthy. Check $HOME/.config/otacon/logs/piper-tts.log"
  return 1
}

install_otacon_tts_piper() {
  local data_dir="${OTACON_PIPER_DATA_DIR:-$HOME/.config/otacon/piper}"
  local port="${OTACON_TTS_PORT:-10200}"
  local endpoint="wyoming://127.0.0.1:${port}"
  mkdir -p "$data_dir"

  stage "6.5t" "START" "Installing Piper TTS (wyoming-piper) for spoken voice preview"
  log "Installing wyoming-piper into the Otacon venv (CPU; spoken Preview requires this)"
  if ! "$VPIP" install --upgrade 'wyoming-piper>=2.5.0'; then
    warn "wyoming-piper pip install failed — voice preview will not speak until Piper is installed"
    OPTIONAL_FAIL=1
    return 1
  fi

  # Pre-download the catalog voices used by Warm Male / Measured Female / Lessac.
  local voices=(
    "en/en_US/lessac/medium/en_US-lessac-medium"
    "en/en_US/bryce/medium/en_US-bryce-medium"
    "en/en_US/hfc_female/medium/en_US-hfc_female-medium"
    "en/en_US/amy/medium/en_US-amy-medium"
  )
  local base="https://huggingface.co/rhasspy/piper-voices/resolve/main"
  local v name
  for v in "${voices[@]}"; do
    name="$(basename "$v")"
    if [[ -f "$data_dir/${name}.onnx" && -f "$data_dir/${name}.onnx.json" ]]; then
      continue
    fi
    log "Downloading Piper voice ${name}"
    curl -fsSL --connect-timeout 30 --max-time 600 \
      -o "$data_dir/${name}.onnx" "${base}/${v}.onnx" || {
      warn "Failed to download ${name}.onnx"
      continue
    }
    curl -fsSL --connect-timeout 30 --max-time 120 \
      -o "$data_dir/${name}.onnx.json" "${base}/${v}.onnx.json" || true
  done

  export OTACON_TTS_PROVIDER=piper
  export OTACON_TTS_ENDPOINT="$endpoint"
  printf '%s\n' "OTACON_TTS_PROVIDER=piper" "OTACON_TTS_ENDPOINT=$endpoint" \
    >"$HOME/.config/otacon/tts.env"
  chmod 644 "$HOME/.config/otacon/tts.env" || true

  write_otacon_tts_unit_draft "$data_dir" "$port" "$(id -un)"
  start_piper_process "$data_dir" "$port"
  sleep 2

  # Quick health probe (non-fatal for install continuation, but marked OPTIONAL_FAIL)
  if piper_health_ok "$endpoint" 3; then
    stage "6.5t" "PASS" "Piper TTS ready at $endpoint"
    ok "Piper TTS listening on $endpoint"
    return 0
  fi
  # Give download/start a bit more time on first run
  sleep 8
  if piper_health_ok "$endpoint" 5; then
    stage "6.5t" "PASS" "Piper TTS ready at $endpoint"
    ok "Piper TTS listening on $endpoint"
    return 0
  fi
  stage "6.5t" "FAIL" "Piper TTS not healthy yet (voice preview may fail until it finishes starting)"
  warn "Piper TTS did not report healthy yet. Check $HOME/.config/otacon/logs/piper-tts.log"
  OPTIONAL_FAIL=1
  return 0
}

mkdir -p "$HOME/.config/otacon/logs"
install_otacon_tts_piper || true

# Capture our hardware recommendation for humans and future tooling.
mkdir -p "$HOME/.config/otacon"
cat > "$HOME/.config/otacon/bootstrap-hardware.env" <<EOF
# Generated by the Antonio G. Garcia / Otaconskeep bootstrap installer.
OTACON_BOOTSTRAP_GPU_NAME=$GPU_NAME
OTACON_BOOTSTRAP_GPU_VRAM_GB=$GPU_VRAM_GB
OTACON_BOOTSTRAP_RAM_GB=$RAM_GB
OTACON_BOOTSTRAP_RECOMMENDED_MODEL=$RECOMMENDED_MODEL
OTACON_BOOTSTRAP_MODEL_ID=$MODEL_ID
OTACON_LLM_ENDPOINT=$OLLAMA_ENDPOINT
OTACON_LLM_MODEL=$RECOMMENDED_MODEL
OTACON_LLM_PROVIDER=ollama
EOF

ok "Python environment ready"

# ------------------------------------------------------------------------------
# Ollama + default chat model (VRAM-sized)
# ------------------------------------------------------------------------------

ensure_ollama_running() {
  if curl -fsS --max-time 2 "$OLLAMA_ENDPOINT/api/tags" >/dev/null 2>&1; then
    return 0
  fi
  if command_exists systemctl && [[ -d /run/systemd/system ]]; then
    if [[ -n "$SUDO" || "${EUID:-$(id -u)}" -eq 0 ]]; then
      $SUDO systemctl enable ollama >/dev/null 2>&1 || true
      $SUDO systemctl restart ollama >/dev/null 2>&1 || true
    else
      # user phase: may lack permission to restart the system unit; try unprivileged status only
      systemctl is-active --quiet ollama 2>/dev/null || true
    fi
  fi
  if ! curl -fsS --max-time 2 "$OLLAMA_ENDPOINT/api/tags" >/dev/null 2>&1; then
    # User-session fallback when systemd unit is missing / not restartable
    mkdir -p "$HOME/.config/otacon"
    nohup ollama serve >"$HOME/.config/otacon/ollama.log" 2>&1 &
    sleep 2
  fi
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "$OLLAMA_ENDPOINT/api/tags" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

write_otacon_llm_config() {
  local model="$1"
  local model_id="$2"
  PYTHONPATH=. "$VPY" - "$model" "$model_id" "$OLLAMA_ENDPOINT" <<'PY'
import json, sys
from pathlib import Path
from core.platform import detect
from core.planner import recommend_hardware_plan
from core.config import build_config, save, load

model, model_id, endpoint = sys.argv[1], sys.argv[2], sys.argv[3]
root = Path.home() / '.config' / 'otacon'
root.mkdir(parents=True, exist_ok=True)
cfg_path = root / 'config.json'

llm = {
    'id': 'service_llm_001',
    'provider': 'ollama',
    'endpoint': endpoint,
    'model': model,
    'model_id': model_id,
}

if cfg_path.is_file():
    try:
        cfg = load(cfg_path)
    except Exception:
        cfg = {}
    cfg['llm_service'] = llm
    if not cfg.get('agents'):
        cfg['agents'] = [
            {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'voice_aria', 'role': 'primary', 'personality': 'friendly'},
        ]
    feats = cfg.setdefault('features', {})
    feats.setdefault('chat', True)
    feats.setdefault('memory', True)
    cfg_path.write_text(json.dumps(cfg, indent=2) + '\n')
else:
    plan = recommend_hardware_plan(detect())
    cfg = build_config(
        plan,
        'Aria',
        ['chat', 'memory'],
        branding={'product_name': 'Otacon', 'tagline': 'Local AI Command System', 'creator': 'Antonio G. Garcia', 'show_creator_credit': True},
        agents=[
            {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'voice_aria', 'role': 'primary', 'personality': 'friendly'},
        ],
        llm_service=llm,
    )
    save(cfg, root)
print(cfg_path)
PY
}

if [[ "$INSTALL_DEFAULT_MODEL" == "1" ]]; then
  stage "6.5" "START" "Installing Ollama + pulling $RECOMMENDED_MODEL"
  log "Default Model: installing Ollama + pulling $RECOMMENDED_MODEL"

  if ! command_exists ollama; then
    if [[ "$INSTALL_PHASE" == "user" ]]; then
      die "Ollama is not installed. The privileged root phase must install it first (Windows: wsl.exe -u root OTACON_INSTALL_PHASE=privileged)."
    fi
    run_watched 300 "ollama install script" -- bash -c 'curl -fsSL --connect-timeout 30 --max-time 240 https://ollama.com/install.sh | sh'
  else
    ok "Ollama already installed"
  fi

  if ensure_ollama_running; then
    ok "Ollama is reachable at $OLLAMA_ENDPOINT"
    log "Pulling $RECOMMENDED_MODEL (sized for ${GPU_VRAM_GB} GB VRAM / $MODEL_TIER)"
    # RTX 4090 selects 14b — can take a long time; heartbeats keep Stage 6 honest.
    if run_watched 3600 "ollama pull $RECOMMENDED_MODEL" --soft -- ollama pull "$RECOMMENDED_MODEL"; then
      ok "Model ready: $RECOMMENDED_MODEL"
      MODEL_OK=1
      stage "6.5" "PASS" "Model ready: $RECOMMENDED_MODEL"
    else
      warn "Could not pull $RECOMMENDED_MODEL."
      warn "Retry later with: ollama pull $RECOMMENDED_MODEL"
      REQUIRED_FAIL=1
      MODEL_OK=0
      stage "6.5" "FAIL" "ollama pull failed or timed out"
    fi
  else
    warn "Ollama installed but did not answer at $OLLAMA_ENDPOINT yet."
    warn "Start it with: sudo systemctl start ollama   (or: ollama serve)"
    warn "Then: ollama pull $RECOMMENDED_MODEL"
    REQUIRED_FAIL=1
    MODEL_OK=0
    stage "6.5" "FAIL" "Ollama API not ready"
  fi

  write_otacon_llm_config "$RECOMMENDED_MODEL" "$MODEL_ID"
  ok "Otacon config points chat at Ollama ($RECOMMENDED_MODEL)"
else
  write_otacon_llm_config "$RECOMMENDED_MODEL" "$MODEL_ID" || true
  warn "Default Model skipped (OTACON_INSTALL_DEFAULT_MODEL=0). Chat needs Ollama later."
  warn "  Re-run with Default Model: OTACON_INSTALL_DEFAULT_MODEL=1 bash install_otacon.sh"
  MODEL_OK=0
  stage "6.5" "INFO" "Default model install skipped"
fi

# ------------------------------------------------------------------------------
# Project tests
# ------------------------------------------------------------------------------

if [[ "$RUN_TESTS" == "1" ]]; then
  log "Running Otacon unit tests"

  if PYTHONPATH=. "$VPY" -m unittest discover -s tests -v; then
    ok "Unit tests passed"
  else
    die "Something in Otacon's self-check failed, so the installer stopped before building anything (safer than shipping something broken). What to do: come share the error text above in Discord ($DISCORD_URL) and someone can help -- this usually isn't something you did wrong."
  fi
fi

# ------------------------------------------------------------------------------
# Deterministic validation suite
# ------------------------------------------------------------------------------

log "Running public architecture validation"

VALIDATORS=(
  validate-resources
  validate-arbiter
  validate-memory
  validate-image
  validate-video
  validate-integrations
  validate-nodes
  validate-hardening
  beta-readiness
)

VALIDATION_WARNINGS=0

for validator in "${VALIDATORS[@]}"; do
  printf '\n\033[1;36m[AGG::VALIDATE]\033[0m %s\n' "$validator"

  if PYTHONPATH=. "$VPY" installer/backend_entry.py "$validator"; then
    ok "$validator"
  else
    warn "$validator returned a non-zero status."
    VALIDATION_WARNINGS=$((VALIDATION_WARNINGS + 1))
    OPTIONAL_FAIL=1
  fi
done

if (( VALIDATION_WARNINGS > 0 )); then
  warn "$VALIDATION_WARNINGS validation command(s) returned warnings/failures."
  warn "Optional architecture validators failing does not by itself fail Core READY."
else
  ok "Architecture validation completed cleanly"
fi

# ------------------------------------------------------------------------------
# Build standalone Python backend required by Tauri
# ------------------------------------------------------------------------------

log "Packaging Otacon backend"

mkdir -p installer/bin .build/pyinstaller

rm -rf .build/pyinstaller/work .build/pyinstaller/dist

"$VENV_DIR/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onefile \
  --name otacon-backend \
  --distpath .build/pyinstaller/dist \
  --workpath .build/pyinstaller/work \
  --specpath .build/pyinstaller \
  --paths "$INSTALL_DIR" \
  --add-data "$INSTALL_DIR/ui:ui" \
  installer/backend_entry.py

install -m 0755 \
  .build/pyinstaller/dist/otacon-backend \
  installer/bin/otacon-backend

ok "Backend packaged: installer/bin/otacon-backend"

# Quick frozen-backend smoke test
log "Smoke-testing packaged backend"

SMOKE_PORT="18787"
SMOKE_LOG=".build/otacon-backend-smoke.log"

OTACON_PORT="$SMOKE_PORT" \
  installer/bin/otacon-backend >"$SMOKE_LOG" 2>&1 &
SMOKE_PID=$!

cleanup_smoke() {
  kill "$SMOKE_PID" >/dev/null 2>&1 || true
  wait "$SMOKE_PID" >/dev/null 2>&1 || true
}
trap cleanup_smoke RETURN

SMOKE_OK=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${SMOKE_PORT}/api/branding" \
       | grep -q '"product_name"'; then
    SMOKE_OK=1
    break
  fi
  sleep 1
done

cleanup_smoke
trap - RETURN

if [[ "$SMOKE_OK" != "1" ]]; then
  cat "$SMOKE_LOG" >&2 || true
  die "Otacon's backend built successfully but didn't respond correctly on its first test run. What to do: check the log printed above, and/or share it in Discord ($DISCORD_URL) for help."
fi

ok "Packaged backend smoke test passed"

# ------------------------------------------------------------------------------
# Rust / Tauri native build
# ------------------------------------------------------------------------------

DEB_PATH=""

if [[ "$BUILD_NATIVE" == "1" ]]; then
  log "Checking Rust toolchain"

  if ! command_exists cargo; then
    log "Rust/Cargo missing; installing rustup toolchain"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --profile minimal

    # shellcheck disable=SC1090
    source "$HOME/.cargo/env"
  fi

  command_exists cargo || die "Rust's installer (rustup) ran, but the 'cargo' tool still isn't visible. What to do: close this terminal completely, open a brand-new one, cd back into $INSTALL_DIR, and rerun this script."
  ok "$(rustc --version)"
  ok "$(cargo --version)"

  if ! command_exists cargo-tauri; then
    log "Tauri CLI v2 missing; installing it"
    cargo install tauri-cli --version "^2.0" --locked
  else
    ok "Tauri CLI already installed"
  fi

  log "Building native Otacon .deb"
  cargo tauri build --config src-tauri/tauri.conf.json

  DEB_PATH="$(
    find src-tauri/target/release/bundle/deb \
      -maxdepth 1 \
      -type f \
      -name '*.deb' \
      -printf '%T@ %p\n' 2>/dev/null \
      | sort -nr \
      | head -n1 \
      | cut -d' ' -f2-
  )"

  if [[ -n "$DEB_PATH" && -f "$DEB_PATH" ]]; then
    ok "Native package built: $DEB_PATH"
  else
    warn "Tauri build completed but no .deb was located in the expected bundle directory."
  fi

  if [[ "$INSTALL_DEB" == "1" && -n "$DEB_PATH" && -f "$DEB_PATH" ]]; then
    if [[ "$INSTALL_PHASE" == "user" ]] || { [[ -z "$SUDO" ]] && [[ "${EUID:-$(id -u)}" -ne 0 ]]; }; then
      warn "Skipping .deb system install in unprivileged phase (package left at $DEB_PATH)"
    else
      log "Installing generated Otacon .deb"
      run_apt 600 "apt-get install otacon .deb" install -y "$DEB_PATH"
      ok "Native package installed"
    fi
  fi
else
  warn "Native Tauri build disabled (OTACON_BUILD_NATIVE=0)."
fi

# ------------------------------------------------------------------------------
# Launch local Otacon web UI
# ------------------------------------------------------------------------------

PID_FILE="$HOME/.config/otacon/wizard.pid"
LOG_FILE="$HOME/.config/otacon/wizard.log"

detect_lan_ip() {
  local ip=""

  if command_exists ip; then
    ip="$(
      ip route get 1.1.1.1 2>/dev/null \
        | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
    )"
  fi

  if [[ -z "$ip" ]] && command_exists hostname; then
    ip="$(
      hostname -I 2>/dev/null \
        | tr ' ' '\n' \
        | awk '/^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)/{print; exit}'
    )"
  fi

  printf '%s\n' "$ip"
}

LAN_IP="$(detect_lan_ip)"
LOCAL_URL="http://127.0.0.1:${CHAT_PORT}"
LAN_URL=""

if [[ "$LAN_MODE" == "1" && -n "$LAN_IP" ]]; then
  LAN_URL="http://${LAN_IP}:${CHAT_PORT}"
fi

SYSTEMD_SERVICE_NAME="otacon.service"
USE_SYSTEMD=0
if command_exists systemctl && [[ -d /run/systemd/system ]]; then
  USE_SYSTEMD=1
fi

# Persist LAN token early so systemd EnvironmentFile can reference it.
LAN_TOKEN_FILE="$HOME/.config/otacon/lan_token"
if [[ "$LAN_MODE" == "1" ]]; then
  mkdir -p "$HOME/.config/otacon"
  if [[ ! -s "$LAN_TOKEN_FILE" ]]; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$LAN_TOKEN_FILE"
    chmod 600 "$LAN_TOKEN_FILE" || true
  fi
  ok "LAN auth token stored at $LAN_TOKEN_FILE"
fi

write_otacon_service_unit() {
  local out_path="$1"
  local run_user="$2"
  local ENV_EXTRA
  local TTS_PROVIDER="${OTACON_TTS_PROVIDER:-piper}"
  local TTS_ENDPOINT="${OTACON_TTS_ENDPOINT:-wyoming://127.0.0.1:10200}"
  if [[ -f "$HOME/.config/otacon/tts.env" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$HOME/.config/otacon/tts.env"; set +a
    TTS_PROVIDER="${OTACON_TTS_PROVIDER:-$TTS_PROVIDER}"
    TTS_ENDPOINT="${OTACON_TTS_ENDPOINT:-$TTS_ENDPOINT}"
  fi
  if [[ "$LAN_MODE" == "1" ]]; then
    ENV_EXTRA="Environment=OTACON_LAN_MODE=1"
  else
    ENV_EXTRA="Environment=OTACON_LAN_MODE=0"
  fi
  cat > "$out_path" <<SERVICEEOF
[Unit]
Description=Otacon AI Ecosystem
After=network.target ollama.service otacon-tts.service
Wants=ollama.service otacon-tts.service

[Service]
Type=simple
User=$run_user
WorkingDirectory=$INSTALL_DIR
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib:/snap/bin:/mnt/c/Program Files/Docker/Docker/resources/bin:/mnt/c/ProgramData/DockerDesktop/version-bin"
Environment=LD_LIBRARY_PATH=/usr/lib/wsl/lib
Environment=PYTHONPATH=$INSTALL_DIR
Environment=OTACON_HOST=$CHAT_HOST
Environment=OTACON_PORT=$CHAT_PORT
$ENV_EXTRA
Environment=OTACON_LLM_PROVIDER=ollama
Environment=OTACON_LLM_ENDPOINT=$OLLAMA_ENDPOINT
Environment=OTACON_LLM_MODEL=$RECOMMENDED_MODEL
Environment=OTACON_TTS_PROVIDER=$TTS_PROVIDER
Environment=OTACON_TTS_ENDPOINT=$TTS_ENDPOINT
Environment=OTACON_SKIP_NVIDIA_SMI=${OTACON_SKIP_NVIDIA_SMI:-0}
ExecStart=$VPY -m installer.server
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEEOF
}

stop_otacon_background() {
  # Always tear down the previous UI process so reinstall picks up new code + TTS env.
  if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
      log "Stopping previous Otacon web UI (PID $OLD_PID) so reinstall loads new code"
      kill "$OLD_PID" >/dev/null 2>&1 || true
      sleep 1
      kill -9 "$OLD_PID" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi
  # Also stop any stray installer.server bound to our port (orphans without pidfile).
  pkill -f "installer.server" 2>/dev/null || true
  sleep 1
}

start_otacon_background() {
  log "Starting your local Otacon web UI"
  local TTS_PROVIDER="${OTACON_TTS_PROVIDER:-piper}"
  local TTS_ENDPOINT="${OTACON_TTS_ENDPOINT:-wyoming://127.0.0.1:10200}"
  if [[ -f "$HOME/.config/otacon/tts.env" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$HOME/.config/otacon/tts.env"; set +a
    TTS_PROVIDER="${OTACON_TTS_PROVIDER:-$TTS_PROVIDER}"
    TTS_ENDPOINT="${OTACON_TTS_ENDPOINT:-$TTS_ENDPOINT}"
  fi
  ensure_otacon_tts_running || warn "Continuing without healthy Piper — Preview will fail until TTS is fixed"
  stop_otacon_background
  nohup env \
    PYTHONPATH="$INSTALL_DIR" \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib:${PATH:-}" \
    LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    OTACON_HOST="$CHAT_HOST" \
    OTACON_PORT="$CHAT_PORT" \
    OTACON_LAN_MODE="$LAN_MODE" \
    OTACON_SKIP_NVIDIA_SMI="${OTACON_SKIP_NVIDIA_SMI:-0}" \
    OTACON_LLM_PROVIDER=ollama \
    OTACON_LLM_ENDPOINT="$OLLAMA_ENDPOINT" \
    OTACON_LLM_MODEL="$RECOMMENDED_MODEL" \
    OTACON_TTS_PROVIDER="$TTS_PROVIDER" \
    OTACON_TTS_ENDPOINT="$TTS_ENDPOINT" \
    "$VPY" -m installer.server \
    >"$LOG_FILE" 2>&1 &
  WIZARD_PID=$!
  printf '%s\n' "$WIZARD_PID" > "$PID_FILE"
}

if [[ "$LAUNCH_WIZARD" == "1" ]]; then
  RUN_USER="$(id -un)"
  SERVICE_DRAFT="$HOME/.config/otacon/$SERVICE_DRAFT_NAME"
  mkdir -p "$HOME/.config/otacon"
  ensure_otacon_tts_running || warn "Piper TTS unhealthy before launching UI"

  if [[ "$INSTALL_PHASE" == "user" ]]; then
    # Unprivileged: write unit draft for finalize (wsl -u root); start process for health check now.
    log "Preparing systemd unit draft for root finalize (no sudoers changes)"
    write_otacon_service_unit "$SERVICE_DRAFT" "$RUN_USER"
    chmod 644 "$SERVICE_DRAFT"
    ok "Service draft written to $SERVICE_DRAFT (finalize phase installs it as root)"
    start_otacon_background
  elif [[ "$USE_SYSTEMD" == "1" ]] && { [[ -n "$SUDO" ]] || [[ "${EUID:-$(id -u)}" -eq 0 ]]; }; then
    log "Installing Otacon as a systemd service (auto-starts, restarts itself on crash)"
    SERVICE_FILE="/etc/systemd/system/$SYSTEMD_SERVICE_NAME"
    write_otacon_service_unit "$SERVICE_DRAFT" "$RUN_USER"
    # Prefer durable Piper unit when draft exists
    if [[ -f "$HOME/.config/otacon/otacon-tts.service.draft" ]]; then
      $SUDO install -m 644 "$HOME/.config/otacon/otacon-tts.service.draft" /etc/systemd/system/otacon-tts.service
    fi
    stop_otacon_background
    $SUDO install -m 644 "$SERVICE_DRAFT" "$SERVICE_FILE"
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable otacon-tts.service >/dev/null 2>&1 || true
    $SUDO systemctl restart otacon-tts.service >/dev/null 2>&1 || true
    $SUDO systemctl enable "$SYSTEMD_SERVICE_NAME" >/dev/null 2>&1 || true
    $SUDO systemctl restart "$SYSTEMD_SERVICE_NAME"
    ok "otacon.service enabled -- starts automatically whenever this Linux environment boots"
  else
    write_otacon_service_unit "$SERVICE_DRAFT" "$RUN_USER" || true
    warn "No live systemd / no root here, so this won't auto-start on the next boot. Falling back to a plain background process for this session."
    start_otacon_background
  fi

  HEALTH_OK=0

  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 \
         "${LOCAL_URL}/api/branding" \
         | grep -q '"product_name"'; then
      HEALTH_OK=1
      break
    fi
    sleep 1
  done

  if [[ "$HEALTH_OK" == "1" ]]; then
    ok "Otacon web UI is online (bind mode: $([[ "$LAN_MODE" == "1" ]] && echo LAN || echo local))"

    printf '\n'
    printf '\033[1;32mOpen Otacon here:\033[0m\n'
    printf '  Local: %s\n' "$LOCAL_URL"

    if [[ "$LAN_MODE" == "1" && -n "$LAN_URL" ]]; then
      printf '  LAN  : %s\n' "$LAN_URL"
      printf '  Auth : Bearer token in %s\n' "$LAN_TOKEN_FILE"
      printf '  Firewall (example ufw): sudo ufw allow from 192.168.0.0/16 to any port %s proto tcp\n' "$CHAT_PORT"
      printf '           or firewalld: sudo firewall-cmd --add-rich-rule='\''rule family=ipv4 source address=192.168.0.0/16 port port=%s protocol=tcp accept'\''\n' "$CHAT_PORT"
    elif [[ "$LAN_MODE" != "1" ]]; then
      printf '  LAN  : disabled (localhost only). Enable with OTACON_LAN_MODE=1\n'
    fi

    printf '\n'

    # Open the browser automatically when a desktop session exists.
    if command_exists xdg-open && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
      xdg-open "$LOCAL_URL" >/dev/null 2>&1 || true
    fi

    # Real end-to-end LLM proof (required when Default Model was selected).
    if [[ "$INSTALL_DEFAULT_MODEL" == "1" && "$MODEL_OK" == "1" ]]; then
      log "End-to-end LLM validation (chat_with_agent → Ollama → inference)"
      E2E_ARGS=(validate-e2e-chat --base-url "$LOCAL_URL")
      if [[ "$LAN_MODE" == "1" && -s "$LAN_TOKEN_FILE" ]]; then
        E2E_ARGS+=(--token "$(cat "$LAN_TOKEN_FILE")")
      fi
      if PYTHONPATH=. "$VPY" installer/backend_entry.py "${E2E_ARGS[@]}"; then
        ok "Real model inference succeeded"
        E2E_OK=1
      else
        warn "End-to-end chat validation FAILED — SYSTEM READY will not be emitted"
        REQUIRED_FAIL=1
        E2E_OK=0
      fi
    elif [[ "$INSTALL_DEFAULT_MODEL" != "1" ]]; then
      warn "Skipping E2E LLM test (Default Model not selected)"
      E2E_OK=1  # not required
    else
      REQUIRED_FAIL=1
      E2E_OK=0
    fi

    # Spoken TTS proof (Aria / voice_aria via Piper). Fail soft → OPTIONAL_FAIL so chat still works,
    # but make it loud — this is the "faint beep" class of bugs. Windows must not claim green READY.
    log "End-to-end TTS validation (Preview → Piper → audible speech)"
    ensure_otacon_tts_running || true
    if [[ -f "$HOME/.config/otacon/tts.env" ]]; then
      # shellcheck disable=SC1090
      set -a; source "$HOME/.config/otacon/tts.env"; set +a
    fi
    if PYTHONPATH=. \
      OTACON_TTS_PROVIDER="${OTACON_TTS_PROVIDER:-piper}" \
      OTACON_TTS_ENDPOINT="${OTACON_TTS_ENDPOINT:-wyoming://127.0.0.1:10200}" \
      "$VPY" -m installer.backend_entry validate-voice --agent Aria --real; then
      ok "Real spoken TTS succeeded (Aria / voice_aria)"
      TTS_E2E_OK=1
    else
      warn "Spoken TTS validation FAILED — Preview will be broken until Piper is healthy"
      warn "  Check: $HOME/.config/otacon/logs/piper-tts.log"
      warn "  Then: otacon doctor   OR OtaconsKeep Setup → Repair (--repair)"
      OPTIONAL_FAIL=1
      TTS_E2E_OK=0
    fi
  else
    warn "Otacon web UI did not answer the health check."
    REQUIRED_FAIL=1
    if [[ "$USE_SYSTEMD" == "1" ]]; then
      warn "Review: sudo journalctl -u $SYSTEMD_SERVICE_NAME -n 100"
    else
      warn "Review: $LOG_FILE"
    fi
  fi
fi

# ------------------------------------------------------------------------------
# Genome Voice Trainer (GPU Piper) — included with normal Otacon install
# Skip: OTACON_INSTALL_VOICE_TRAINER=0
# Also SKIP (not DEGRADED) when NVIDIA capability is absent — GPU-only feature.
# ------------------------------------------------------------------------------
VOICE_TRAINER_SKIPPED=0
VOICE_TRAINER_SKIP_REASON=""
if [[ "$INSTALL_VOICE_TRAINER" == "1" ]]; then
  # WSL systemd PATH often hides nvidia-smi under /usr/lib/wsl/lib (same trap as Expansion).
  _vt_smi_user=""
  if command_exists nvidia-smi; then _vt_smi_user="$(command -v nvidia-smi)"
  elif [[ -x /usr/lib/wsl/lib/nvidia-smi ]]; then _vt_smi_user=/usr/lib/wsl/lib/nvidia-smi
  elif [[ -x /usr/bin/nvidia-smi ]]; then _vt_smi_user=/usr/bin/nvidia-smi
  fi
  if [[ -z "$_vt_smi_user" ]] || ! PATH="/usr/lib/wsl/lib:${PATH:-}" LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$_vt_smi_user" >/dev/null 2>&1; then
    VOICE_TRAINER_SKIPPED=1
    VOICE_TRAINER_SKIP_REASON="no usable NVIDIA GPU (nvidia-smi)"
    warn "Voice Trainer SKIPPED — ${VOICE_TRAINER_SKIP_REASON}."
    warn "  GPU features require NVIDIA drivers + nvidia-smi. Core install continues."
    warn "  Later (on a GPU host): curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash"
    warn "  Tip: Fix-Otacon-GPU.bat if Windows has a GPU but WSL nvidia-smi fails."
    VOICE_TRAINER_OK=0
  elif [[ -f "$PRIV_MARKER" ]] && grep -q '^voice_trainer=ok' "$PRIV_MARKER" 2>/dev/null; then
    ok "Genome Voice Trainer already installed in privileged phase"
    VOICE_TRAINER_OK=1
  elif [[ -d "${HOME}/otacon-voice-trainer" ]] && docker image inspect piper-voice-trainer:gpu >/dev/null 2>&1; then
    ok "Genome Voice Trainer already present ($HOME/otacon-voice-trainer)"
    VOICE_TRAINER_OK=1
  elif [[ "${EUID:-$(id -u)}" -ne 0 ]] && ! sudo -n true >/dev/null 2>&1; then
    # User phase on Windows has no TTY and no NOPASSWD:ALL — never call VT here
    # (its old installer hung forever on `sudo apt-get`). Privileged phase owns apt.
    VOICE_TRAINER_SKIPPED=1
    VOICE_TRAINER_SKIP_REASON="needs root apt/docker (run via privileged phase or: wsl -u root)"
    warn "Voice Trainer SKIPPED in user phase — ${VOICE_TRAINER_SKIP_REASON}."
    warn "  OtaconsKeep Setup installs it during the root bootstrap when a GPU is present."
    warn "  Manual: wsl.exe -u root -- bash -lc 'OTACON_VT_DIR=$HOME/otacon-voice-trainer OTACON_VT_SKIP_UI=1 curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash'"
    VOICE_TRAINER_OK=0
  else
    log "Voice Trainer: installing Genome GPU Piper (included with Otacon)"
    if curl -fsSL "$VOICE_TRAINER_INSTALLER_URL" | bash; then
      ok "Genome Voice Trainer installed"
      VOICE_TRAINER_OK=1
    else
      warn "Genome Voice Trainer install failed — treated as optional DEGRADED component."
      warn "  NVIDIA was detected; this is a real optional-component failure (not a skip)."
      warn "  Retry with: curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash"
      OPTIONAL_FAIL=1
      VOICE_TRAINER_OK=0
    fi
  fi
else
  warn "Voice Trainer skipped (OTACON_INSTALL_VOICE_TRAINER=0)."
  warn "  Standalone later: curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash"
  VOICE_TRAINER_OK=0
fi

# Install otacon CLI helper (doctor)
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/otacon" <<CLIEOF
#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR}"
VPY="${VENV_DIR}/bin/python"
export PYTHONPATH="\$INSTALL_DIR"
case "\${1:-}" in
  doctor|"") exec "\$VPY" -m installer.backend_entry doctor "\${@:2}" ;;
  *) exec "\$VPY" -m installer.backend_entry "\$@" ;;
esac
CLIEOF
chmod +x "$HOME/.local/bin/otacon"
ok "CLI helper: ~/.local/bin/otacon doctor"

# ------------------------------------------------------------------------------
# Final summary — READY / DEGRADED / FAILED
# ------------------------------------------------------------------------------

FINAL_STATE=READY
FINAL_RC=0
if [[ "$REQUIRED_FAIL" == "1" ]] || [[ "$LAUNCH_WIZARD" == "1" && "$HEALTH_OK" != "1" ]]; then
  FINAL_STATE=FAILED
  FINAL_RC=1
elif [[ "$OPTIONAL_FAIL" == "1" ]]; then
  FINAL_STATE=DEGRADED
  FINAL_RC=2
fi

# When Default Model selected, READY requires real E2E inference.
if [[ "$INSTALL_DEFAULT_MODEL" == "1" && "$E2E_OK" != "1" ]]; then
  FINAL_STATE=FAILED
  FINAL_RC=1
fi

printf '\n\033[1;35m'
case "$FINAL_STATE" in
  READY)
    if [[ "$VOICE_TRAINER_SKIPPED" == "1" ]]; then
      cat <<'DONE_ASCII'
==============================================================================
              OTACON AI ECOSYSTEM // CORE PASS
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
              GPU FEATURES SKIPPED (NO NVIDIA)
==============================================================================
DONE_ASCII
    else
      cat <<'DONE_ASCII'
==============================================================================
              OTACON AI ECOSYSTEM // INSTALL COMPLETE
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
                           SYSTEM READY
==============================================================================
DONE_ASCII
    fi
    ;;
  DEGRADED)
    cat <<'DONE_ASCII'
==============================================================================
              OTACON AI ECOSYSTEM // INSTALL DEGRADED
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
              CORE UP — OPTIONAL COMPONENT FAILED
==============================================================================
DONE_ASCII
    ;;
  *)
    cat <<'DONE_ASCII'
==============================================================================
              OTACON AI ECOSYSTEM // INSTALL FAILED
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
              REQUIRED VALIDATION DID NOT PASS
==============================================================================
DONE_ASCII
    ;;
esac
printf '\033[0m'

printf 'Final state      : %s (exit %s)\n' "$FINAL_STATE" "$FINAL_RC"
printf 'Install log      : %s\n' "$INSTALL_LOG"
printf 'Repository       : %s\n' "$INSTALL_DIR"
printf 'Python venv      : %s\n' "$VENV_DIR"
printf 'Detected GPU     : %s\n' "$GPU_NAME"
printf 'Detected VRAM    : %s GB\n' "$GPU_VRAM_GB"
printf 'Default LLM      : %s (%s)\n' "$RECOMMENDED_MODEL" "$MODEL_TIER"
printf 'Profile          : %s (native=%s)\n' "$OTACON_PROFILE" "$BUILD_NATIVE"
printf 'LAN mode         : %s\n' "$([[ "$LAN_MODE" == "1" ]] && echo enabled || echo local-only)"
if [[ "$INSTALL_DEFAULT_MODEL" == "1" ]]; then
  printf 'Default Model    : %s (Ollama @ %s)\n' "$([[ "$MODEL_OK" == "1" ]] && echo installed || echo FAILED)" "$OLLAMA_ENDPOINT"
  printf 'E2E LLM proof    : %s\n' "$([[ "$E2E_OK" == "1" ]] && echo PASS || echo FAIL)"
else
  printf 'Default Model    : skipped (OTACON_INSTALL_DEFAULT_MODEL=0)\n'
fi
printf 'E2E TTS proof    : %s\n' "$([[ "$TTS_E2E_OK" == "1" ]] && echo PASS || echo FAIL/pending)"
if [[ "$INSTALL_VOICE_TRAINER" == "1" ]]; then
  if [[ "$VOICE_TRAINER_SKIPPED" == "1" ]]; then
    printf 'Voice Trainer    : SKIPPED (%s)\n' "$VOICE_TRAINER_SKIP_REASON"
    printf 'GPU features     : SKIPPED (capability absent — not a failure)\n'
  else
    printf 'Voice Trainer    : %s\n' "$([[ "$VOICE_TRAINER_OK" == "1" ]] && echo OK || echo FAILED/optional)"
  fi
else
  printf 'Voice Trainer    : skipped (OTACON_INSTALL_VOICE_TRAINER=0)\n'
fi
printf 'Local web UI     : %s
' "$LOCAL_URL"
if [[ "$USE_SYSTEMD" == "1" ]]; then
  printf 'Auto-start       : systemd (%s) -- survives reboots and crashes on its own\n' "$SYSTEMD_SERVICE_NAME"
  printf 'Service log      : sudo journalctl -u %s -f\n' "$SYSTEMD_SERVICE_NAME"
else
  printf 'Wizard log       : %s\n' "$LOG_FILE"
fi
printf 'Hardware profile : %s\n' "$HOME/.config/otacon/bootstrap-hardware.env"
printf 'Doctor           : ~/.local/bin/otacon doctor\n'

if [[ -n "$DEB_PATH" ]]; then
  printf 'Native .deb      : %s\n' "$DEB_PATH"
fi

printf '\n'
printf '\033[1;33mYou are running Otacon Core -- free, open source, self-hosted.\033[0m\n'
printf '\033[1;33mQuestions, help, and Otaconskeep Services (architecture, deployment,\033[0m\n'
printf '\033[1;33msupport) all live in one place -- come say hi: %s\033[0m\n' "$DISCORD_URL"
printf '\n'
printf '[ANTONIO G. GARCIA] Rerunning this installer is safe; completed prerequisites are reused.\n'
if [[ "$FINAL_RC" -eq 0 ]]; then
  printf '[ANTONIO G. GARCIA] Otacon bootstrap complete. Welcome to the Keep.\n'
elif [[ "$FINAL_RC" -eq 2 ]]; then
  printf '[ANTONIO G. GARCIA] Otacon core is up but degraded. Check the log and optional components.\n'
else
  printf '[ANTONIO G. GARCIA] Otacon install did not reach READY. See log: %s\n' "$INSTALL_LOG"
fi
emit_phase_exit "$FINAL_RC" "final-state=$FINAL_STATE"
exit "$FINAL_RC"
