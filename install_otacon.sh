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
#   - Launches the setup wizard and checks http://127.0.0.1:8787
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
if [[ "$LAN_MODE" == "1" || "${LAN_MODE,,}" == "true" || "${LAN_MODE,,}" == "yes" || "${LAN_MODE,,}" == "lan" ]]; then
  LAN_MODE=1
  CHAT_HOST="${OTACON_CHAT_HOST:-0.0.0.0}"
else
  LAN_MODE=0
  CHAT_HOST="${OTACON_CHAT_HOST:-127.0.0.1}"
fi
CHAT_PORT="${OTACON_CHAT_PORT:-5757}"
VOICE_TRAINER_INSTALLER_URL="${OTACON_VOICE_TRAINER_URL:-https://raw.githubusercontent.com/Otaconskeep/otacon-voice-trainer/main/install_voice_trainer.sh}"
OLLAMA_ENDPOINT="${OTACON_LLM_ENDPOINT:-http://127.0.0.1:11434}"
ALLOW_UNSUPPORTED_OS="${OTACON_ALLOW_UNSUPPORTED_OS:-0}"

# Install outcome tracking
REQUIRED_FAIL=0
OPTIONAL_FAIL=0
MODEL_OK=0
E2E_OK=0
HEALTH_OK=0
VOICE_TRAINER_OK=0
INSTALL_LOG_DIR="${OTACON_INSTALL_LOG_DIR:-$HOME/.config/otacon/logs}"
mkdir -p "$INSTALL_LOG_DIR"
INSTALL_LOG="$INSTALL_LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$INSTALL_LOG") 2>&1

log()  { printf '\n\033[1;36m[AGG::OTACON]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[AGG::OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[AGG::WARN]\033[0m %s\n' "$*" >&2; }
die()  {
  printf '\033[1;31m[AGG::FAIL]\033[0m %s\n' "$*" >&2
  printf '\033[1;31m[AGG::FAIL]\033[0m Failed stage near line %s. Log: %s\n' "${BASH_LINENO[0]:-$LINENO}" "$INSTALL_LOG" >&2
  printf 'Recovery: re-run this installer, or: PYTHONPATH=%s %s/bin/python -m installer.backend_entry doctor\n' \
    "${INSTALL_DIR:-$HOME/otacon-ai-ecosystem}" "${VENV_DIR:-$HOME/otacon-ai-ecosystem/.venv}" >&2
  exit 1
}

# Machine-parseable stage markers for the Windows UI (and humans).
# Format: [STAGE] <id> <status> <detail>
# status: START | PASS | FAIL | WAIT | INFO
stage() {
  local id="$1" status="$2"; shift 2
  printf '[STAGE] %s %s %s\n' "$id" "$status" "$*"
  printf '[AGG::PROGRESS] [%s] %s — %s\n' "$id" "$status" "$*"
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

run_apt() {
  # Bounded, noninteractive apt with heartbeats. Never waits on a TTY prompt.
  local timeout_sec="$1"; shift
  local label="$1"; shift
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE="${NEEDRESTART_MODE:-a}"
  export APT_LISTCHANGES_FRONTEND=none
  wait_for_apt_lock 180
  # shellcheck disable=SC2086
  run_watched "$timeout_sec" "$label" -- $SUDO env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a \
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
  warn "Running the whole installer as root is not recommended."
  warn "Use a normal user account; sudo will be requested only for system packages."
fi

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if command_exists sudo; then
    SUDO="sudo"
  else
    die "This installer needs 'sudo' to install a few system packages, and it isn't available for your user. What to do: ask whoever set up this computer to add your account to the sudo group (on Ubuntu: 'usermod -aG sudo yourusername', then log out and back in), then rerun this script."
  fi
fi

# Unattended Windows→WSL installs have no TTY. A password prompt here hangs forever
# with the last visible line stuck on "Checking Linux build dependencies".
if [[ -n "$SUDO" ]]; then
  stage "6.0" "START" "Verifying passwordless sudo (required for unattended install)"
  if ! $SUDO -n true >/dev/null 2>&1; then
    stage "6.0" "FAIL" "sudo requires a password (no TTY available)"
    die "sudo needs a password, but Otacon Setup runs unattended from Windows with no keyboard prompt. That is why Stage 6 can sit forever after 'Checking Linux build dependencies'. Fix (one-time, inside Ubuntu): run 'sudo -v' once to confirm your password works, then: echo \"\$(whoami) ALL=(ALL) NOPASSWD:ALL\" | sudo tee /etc/sudoers.d/otacon-nopasswd && sudo chmod 440 /etc/sudoers.d/otacon-nopasswd — then double-click OtaconsKeep-Setup.bat again. Log: $INSTALL_LOG"
  fi
  SUDO="$SUDO -n"
  stage "6.0" "PASS" "passwordless sudo OK"
  ok "sudo is passwordless (safe for unattended install)"
fi

# ------------------------------------------------------------------------------
# WSL: make sure systemd is active before doing anything else. Enabling it
# only takes effect on the *next* boot of this WSL distro (not a Windows
# reboot -- just this Linux environment restarting), so if we just turned it
# on, stop here with a distinct exit code. The Windows-side installer
# (install_otacon.bat) restarts WSL and reruns this script automatically;
# every step below is safe to redo, so the rerun just picks up from here.
# ------------------------------------------------------------------------------

if grep -qi microsoft /proc/version 2>/dev/null; then
  WSL_CONF="/etc/wsl.conf"
  if ! grep -qE '^\s*systemd\s*=\s*true' "$WSL_CONF" 2>/dev/null; then
    log "Enabling systemd in WSL (needed so Otacon can auto-start with Windows)"
    if [[ -f "$WSL_CONF" ]] && grep -q '^\[boot\]' "$WSL_CONF"; then
      $SUDO sed -i '/^\[boot\]/a systemd=true' "$WSL_CONF"
    else
      printf '[boot]\nsystemd=true\n' | $SUDO tee -a "$WSL_CONF" >/dev/null
    fi
    warn "This Linux environment needs to restart once to activate that. If you're seeing this from install_otacon.bat, it will handle the restart and continue automatically."
    exit 42
  fi
fi

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
  warn "If Windows nvidia-smi shows an RTX card but this does not, install/update the NVIDIA Windows driver and ensure WSL2 GPU support is enabled, then reopen Ubuntu."
fi

stage "6.3" "START" "Installing Linux build dependencies via apt"
log "Checking Linux build dependencies"

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export APT_LISTCHANGES_FRONTEND=none

APT_PACKAGES=(
  ca-certificates
  curl
  file
  git
  build-essential
  pkg-config
  python3
  python3-venv
  python3-pip
  libssl-dev
  zstd
)

# Native/desktop profile needs WebKit/Tauri libs; Core skips them to reduce failure surface.
if [[ "$BUILD_NATIVE" == "1" ]]; then
  APT_PACKAGES+=(
    libwebkit2gtk-4.1-dev
    libayatana-appindicator3-dev
    librsvg2-dev
    libxdo-dev
  )
fi

printf '[AGG::PROGRESS] apt packages (%s): %s\n' "${#APT_PACKAGES[@]}" "${APT_PACKAGES[*]}"
run_apt 600 "apt-get update" update -y
run_apt 1200 "apt-get install build dependencies" install -y "${APT_PACKAGES[@]}"
stage "6.3" "PASS" "Linux build dependencies installed"
ok "System dependencies are installed"

# ------------------------------------------------------------------------------
# Git clone / update
# ------------------------------------------------------------------------------

log "Synchronizing Otacon public repository"
stage "6.4" "START" "Cloning/updating Otacon repository"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  run_watched 300 "git fetch" -- git -C "$INSTALL_DIR" fetch --prune origin
  CURRENT_BRANCH="$(git -C "$INSTALL_DIR" branch --show-current || true)"

  if [[ "$CURRENT_BRANCH" == "main" ]]; then
    run_watched 300 "git pull" -- git -C "$INSTALL_DIR" pull --ff-only
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

# psutil is optional in source but improves hardware reporting.
"$VPIP" install --upgrade psutil pyinstaller

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
    $SUDO systemctl enable ollama >/dev/null 2>&1 || true
    $SUDO systemctl restart ollama >/dev/null 2>&1 || true
  fi
  if ! curl -fsS --max-time 2 "$OLLAMA_ENDPOINT/api/tags" >/dev/null 2>&1; then
    # User-session fallback when systemd unit is missing
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
            {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001', 'role': 'primary', 'personality': 'friendly'},
            {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002', 'role': 'secondary', 'personality': 'friendly'},
        ]
    feats = cfg.setdefault('features', {})
    feats.setdefault('chat', True)
    feats.setdefault('memory', True)
    cfg_path.write_text(json.dumps(cfg, indent=2) + '\n')
else:
    plan = recommend_hardware_plan(detect())
    cfg = build_config(
        plan,
        'Billy',
        ['chat', 'memory'],
        branding={'product_name': 'Otacon', 'tagline': 'Local AI Command System', 'creator': 'Antonio G. Garcia', 'show_creator_credit': True},
        agents=[
            {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001', 'role': 'primary', 'personality': 'friendly'},
            {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002', 'role': 'secondary', 'personality': 'friendly'},
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
    log "Installing generated Otacon .deb"
    run_apt 600 "apt-get install otacon .deb" install -y "$DEB_PATH"
    ok "Native package installed"
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

if [[ "$LAUNCH_WIZARD" == "1" ]]; then
  if [[ "$USE_SYSTEMD" == "1" ]]; then
    log "Installing Otacon as a systemd service (auto-starts, restarts itself on crash)"

    SERVICE_FILE="/etc/systemd/system/$SYSTEMD_SERVICE_NAME"
    RUN_USER="$(id -un)"
    ENV_EXTRA=""
    if [[ "$LAN_MODE" == "1" ]]; then
      ENV_EXTRA="Environment=OTACON_LAN_MODE=1"
    else
      ENV_EXTRA="Environment=OTACON_LAN_MODE=0"
    fi

    $SUDO tee "$SERVICE_FILE" >/dev/null <<SERVICEEOF
[Unit]
Description=Otacon AI Ecosystem
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
Environment=OTACON_HOST=$CHAT_HOST
Environment=OTACON_PORT=$CHAT_PORT
$ENV_EXTRA
Environment=OTACON_LLM_PROVIDER=ollama
Environment=OTACON_LLM_ENDPOINT=$OLLAMA_ENDPOINT
Environment=OTACON_LLM_MODEL=$RECOMMENDED_MODEL
ExecStart=$VPY -m installer.server
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEEOF

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable "$SYSTEMD_SERVICE_NAME" >/dev/null 2>&1 || true
    $SUDO systemctl restart "$SYSTEMD_SERVICE_NAME"
    ok "otacon.service enabled -- starts automatically whenever this Linux environment boots"
  else
    log "Starting your local Otacon web UI"
    warn "No live systemd found here, so this won't auto-start on the next boot. Falling back to a plain background process for this session."

    if [[ -f "$PID_FILE" ]]; then
      OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
      if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1 \
        && curl -fsS --max-time 2 "${LOCAL_URL}/api/branding" 2>/dev/null | grep -q '"product_name"'; then
        ok "Otacon web UI is already running (PID $OLD_PID)"
      else
        warn "Stale or unhealthy Otacon PID file — restarting web UI"
        if [[ -n "$OLD_PID" ]]; then kill "$OLD_PID" >/dev/null 2>&1 || true; fi
        rm -f "$PID_FILE"
      fi
    fi

    if [[ ! -f "$PID_FILE" ]]; then
      nohup env \
        PYTHONPATH="$INSTALL_DIR" \
        OTACON_HOST="$CHAT_HOST" \
        OTACON_PORT="$CHAT_PORT" \
        OTACON_LAN_MODE="$LAN_MODE" \
        OTACON_LLM_PROVIDER=ollama \
        OTACON_LLM_ENDPOINT="$OLLAMA_ENDPOINT" \
        OTACON_LLM_MODEL="$RECOMMENDED_MODEL" \
        "$VPY" -m installer.server \
        >"$LOG_FILE" 2>&1 &

      WIZARD_PID=$!
      printf '%s\n' "$WIZARD_PID" > "$PID_FILE"
    fi
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
  if ! command_exists nvidia-smi || ! nvidia-smi >/dev/null 2>&1; then
    VOICE_TRAINER_SKIPPED=1
    VOICE_TRAINER_SKIP_REASON="no usable NVIDIA GPU (nvidia-smi)"
    warn "Voice Trainer SKIPPED — ${VOICE_TRAINER_SKIP_REASON}."
    warn "  GPU features require NVIDIA drivers + nvidia-smi. Core install continues."
    warn "  Later (on a GPU host): curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash"
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
exit "$FINAL_RC"
