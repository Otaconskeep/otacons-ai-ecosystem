#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
#  OTACONSKEEP // OTACON AI ECOSYSTEM -- LITE EDITION
#  AUTOMATED ONE-COMMAND BOOTSTRAP + NATIVE BUILDER (free, full source)
#
#  Designed & Engineered by Antonio G. Garcia
#  "Built for the Keep."
#  Community, support, and Premium Edition: https://discord.gg/cZDeqECzX
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
#
# Rerunnable:
#   - Existing repo -> fast-forward update
#   - Existing venv -> reused
#   - Existing Rust/Cargo/Tauri -> reused
#   - Existing OS packages -> apt skips them
#
# Environment overrides:
#   OTACON_INSTALL_DIR="$HOME/otacon-ai-ecosystem"
#   OTACON_BUILD_NATIVE=1
#   OTACON_INSTALL_DEB=0
#   OTACON_LAUNCH_WIZARD=1
#   OTACON_INSTALL_STT=0
#   OTACON_RUN_TESTS=1
#
# Notes:
#   The current public repository still marks real Ollama/Piper acceptance and
#   some production providers as pending external validation. This installer
#   automates the repository's actual public build/runtime path without
#   pretending those unfinished integrations are production-ready.
# ==============================================================================

BRAND="ANTONIO G. GARCIA // OTACONSKEEP"
PRODUCT="OTACON AI ECOSYSTEM -- LITE EDITION"
TAGLINE="Built for the Keep."
DISCORD_URL="https://discord.gg/cZDeqECzX"

REPO_URL="https://github.com/Otaconskeep/otacons-ai-ecosystem.git"
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
VENV_DIR="$INSTALL_DIR/.venv"

BUILD_NATIVE="${OTACON_BUILD_NATIVE:-1}"
INSTALL_DEB="${OTACON_INSTALL_DEB:-0}"
LAUNCH_WIZARD="${OTACON_LAUNCH_WIZARD:-1}"
INSTALL_STT="${OTACON_INSTALL_STT:-0}"
RUN_TESTS="${OTACON_RUN_TESTS:-1}"
CHAT_HOST="${OTACON_CHAT_HOST:-0.0.0.0}"
CHAT_PORT="${OTACON_CHAT_PORT:-5757}"

log()  { printf '\n\033[1;36m[AGG::OTACON]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[AGG::OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[AGG::WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[AGG::FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

trap 'printf "\n\033[1;31m[AGG::FAIL]\033[0m Installer stopped on line %s.\n" "$LINENO" >&2' ERR

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
printf '\033[0;37m%s — %s\033[0m\n' "$PRODUCT" "$TAGLINE"
printf '\033[0;37mThis is the free Lite Edition -- full source, no license key, no time limit.\033[0m\n'
printf '\033[0;37mPremium (extra models, priority support, more) -- come say hi: %s\033[0m\n\n' "$DISCORD_URL"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

is_debian_family() {
  [[ -f /etc/os-release ]] || return 1
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" || "${ID_LIKE:-}" == *"debian"* ]]
}

is_debian_family || die \
  "This computer isn't running Ubuntu or Debian Linux, which is what this installer needs. What to do: if you're on Windows or Mac, you'll need an Ubuntu machine or VM to run Otacon Lite right now (support for other systems is planned) -- ask in Discord ($DISCORD_URL) if you're not sure how to set one up."

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

# Mirror the public project's broad model recommendation:
# >= 8 GB NVIDIA VRAM -> qwen2.5:7b; otherwise -> qwen2.5:1.5b
RECOMMENDED_MODEL="qwen2.5:1.5b"
MODEL_TIER="Conversational Small"

if awk -v v="$GPU_VRAM_GB" 'BEGIN{exit !(v>=8)}'; then
  RECOMMENDED_MODEL="qwen2.5:7b"
  MODEL_TIER="Conversational Standard"
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
printf '  Model hint  : %s\n' "$RECOMMENDED_MODEL"

# ------------------------------------------------------------------------------
# System packages
# ------------------------------------------------------------------------------

log "Checking Linux build dependencies"

export DEBIAN_FRONTEND=noninteractive

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
  libwebkit2gtk-4.1-dev
  libayatana-appindicator3-dev
  librsvg2-dev
  libxdo-dev
)

$SUDO apt-get update -y
$SUDO apt-get install -y "${APT_PACKAGES[@]}"

ok "System dependencies are installed"

# ------------------------------------------------------------------------------
# Git clone / update
# ------------------------------------------------------------------------------

log "Synchronizing Otacon public repository"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch --prune origin
  CURRENT_BRANCH="$(git -C "$INSTALL_DIR" branch --show-current || true)"

  if [[ "$CURRENT_BRANCH" == "main" ]]; then
    git -C "$INSTALL_DIR" pull --ff-only
  else
    warn "Repository is on branch '${CURRENT_BRANCH:-detached}'."
    warn "Leaving local branch selection untouched; fetched origin only."
  fi
elif [[ -e "$INSTALL_DIR" ]]; then
  die "$INSTALL_DIR already exists but isn't an Otacon install this script recognizes. What to do: rename or delete that folder (if it's not something you need), or set OTACON_INSTALL_DIR=/some/other/path before rerunning this script to install somewhere else."
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

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
else
  warn "Faster-Whisper installation skipped (OTACON_INSTALL_STT=0)."
  warn "The current repository still marks real STT/model loading as external acceptance work."
fi

# Capture our hardware recommendation for humans and future tooling.
mkdir -p "$HOME/.config/otacon"
cat > "$HOME/.config/otacon/bootstrap-hardware.env" <<EOF
# Generated by the Antonio G. Garcia / Otaconskeep bootstrap installer.
OTACON_BOOTSTRAP_GPU_NAME=$GPU_NAME
OTACON_BOOTSTRAP_GPU_VRAM_GB=$GPU_VRAM_GB
OTACON_BOOTSTRAP_RAM_GB=$RAM_GB
OTACON_BOOTSTRAP_RECOMMENDED_MODEL=$RECOMMENDED_MODEL
EOF

ok "Python environment ready"

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
  fi
done

if (( VALIDATION_WARNINGS > 0 )); then
  warn "$VALIDATION_WARNINGS validation command(s) returned warnings/failures."
  warn "This does not automatically mean the bootstrap failed; some public-provider acceptance paths are intentionally pending."
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
    $SUDO apt-get install -y "$DEB_PATH"
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

if [[ -n "$LAN_IP" ]]; then
  LAN_URL="http://${LAN_IP}:${CHAT_PORT}"
fi

if [[ "$LAUNCH_WIZARD" == "1" ]]; then
  log "Starting your local Otacon web UI"

  if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
      ok "Otacon web UI is already running (PID $OLD_PID)"
    else
      rm -f "$PID_FILE"
    fi
  fi

  if [[ ! -f "$PID_FILE" ]]; then
    nohup env \
      PYTHONPATH="$INSTALL_DIR" \
      OTACON_HOST="$CHAT_HOST" \
      OTACON_PORT="$CHAT_PORT" \
      "$VPY" -m installer.server \
      >"$LOG_FILE" 2>&1 &

    WIZARD_PID=$!
    printf '%s\n' "$WIZARD_PID" > "$PID_FILE"
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
    ok "Otacon web UI is online"

    printf '\n'
    printf '\033[1;32mOpen Otacon here:\033[0m\n'
    printf '  Local: %s\n' "$LOCAL_URL"

    if [[ -n "$LAN_URL" ]]; then
      printf '  LAN  : %s\n' "$LAN_URL"
    fi

    printf '\n'

    # Open the browser automatically when a desktop session exists.
    if command_exists xdg-open && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
      xdg-open "$LOCAL_URL" >/dev/null 2>&1 || true
    fi
  else
    warn "Otacon web UI did not answer the health check."
    warn "Review: $LOG_FILE"
  fi
fi

# ------------------------------------------------------------------------------
# Final summary
# ------------------------------------------------------------------------------

printf '\n\033[1;35m'
cat <<'DONE_ASCII'
==============================================================================
              OTACON AI ECOSYSTEM // INSTALL COMPLETE
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
                           SYSTEM READY
==============================================================================
DONE_ASCII
printf '\033[0m'

printf 'Repository       : %s\n' "$INSTALL_DIR"
printf 'Python venv      : %s\n' "$VENV_DIR"
printf 'Detected GPU     : %s\n' "$GPU_NAME"
printf 'Detected VRAM    : %s GB\n' "$GPU_VRAM_GB"
printf 'Recommended LLM  : %s\n' "$RECOMMENDED_MODEL"
printf 'Local web UI     : %s
' "$LOCAL_URL"
printf 'Wizard log       : %s\n' "$LOG_FILE"
printf 'Hardware profile : %s\n' "$HOME/.config/otacon/bootstrap-hardware.env"

if [[ -n "$DEB_PATH" ]]; then
  printf 'Native .deb      : %s\n' "$DEB_PATH"
fi

printf '\n'
printf '\033[1;33mYou are running the free Lite Edition.\033[0m\n'
printf '\033[1;33mQuestions, help, and the Premium Edition (extra models, priority support,\033[0m\n'
printf '\033[1;33mmore) all live in one place -- come say hi: %s\033[0m\n' "$DISCORD_URL"
printf '\n'
printf '[ANTONIO G. GARCIA] Rerunning this installer is safe; completed prerequisites are reused.\n'
printf '[ANTONIO G. GARCIA] Otacon bootstrap complete. Welcome to the Keep.\n'
