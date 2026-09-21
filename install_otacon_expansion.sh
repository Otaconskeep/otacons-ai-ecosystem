#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
#  OTACONSKEEP // OTACON AI ECOSYSTEM -- OTACON EXPANSION (foundation layer)
#  ONE-COMMAND INSTALL FOR THE CANONICAL AGENT SCHEMA + DEFAULT ROSTER
#
#  Designed & Engineered by Antonio G. Garcia
#  "Built for the Keep."
#  Community, support, and Otaconskeep Services: https://discord.gg/cZDeqECzX
# ==============================================================================
#
# READ THIS FIRST:
#   Otacon Expansion is still in development. This script installs and
#   verifies the foundation layer: versioned agent schema, bounded
#   relationship/mood formulas, motion-manifest schema, decision audit
#   records, readiness state, and a schema-valid five-agent default roster
#   (Aria/Vector/Ledger/Muse/Sentry) written to disk.
#
#   UI floors (Dashboard, Codec, War Room, Learning, etc.) exist in source
#   and may be reachable after entitlement + Core restart. This installer
#   only claims "Foundation installed" — not full Expansion-ready — until
#   entitlement and feature smoke checks pass. Optional integrations
#   (Discord/HA/n8n) remain unconfigured unless the owner sets them up.
#   Nothing here overwrites or gates Otacon Core.
#   Full status: https://otaconskeep.github.io/expansion/
#
# What this installer does:
#   - Confirms Otacon Core is already installed (Expansion installs on top
#     of it, never standalone)
#   - Fast-forwards the same public repository Core already cloned
#   - Reuses Core's existing Python virtual environment
#   - Runs the expansion/ test suite as a real acceptance gate (currently
#     50 tests: schema, hierarchy, relationship formulas, motion manifest,
#     decision audit, readiness, default-roster seeding)
#   - Generates and schema-validates the five default agents, and validates
#     the reporting hierarchy has no cycles
#   - Writes the validated roster to ~/.config/otacon/expansion/agents/
#
# Rerunnable:
#   - Existing repo -> fast-forward update, same as Core's installer
#   - Existing seed files -> re-validated and rewritten; created_at of each
#     agent is preserved across reruns, only updated_at moves forward
#
# Environment overrides:
#   OTACON_INSTALL_DIR="$HOME/otacon-ai-ecosystem"   # must match your Core install
#   OTACON_EXPANSION_DATA_DIR="$HOME/.config/otacon/expansion/agents"
#   OTACON_RUN_TESTS=1                                # set 0 to skip the acceptance gate (not recommended)
#
# Final states / exit codes:
#   FOUNDATION READY    (0) — schema/tests/seed all passed
#   FOUNDATION DEGRADED (2) — seed roster written, but the test suite did not fully pass
#   FOUNDATION FAILED   (1) — Core missing, repo sync failed, or the roster failed validation
# ==============================================================================

BRAND="ANTONIO G. GARCIA // OTACONSKEEP"
PRODUCT="OTACON AI ECOSYSTEM -- OTACON EXPANSION (foundation layer)"
TAGLINE="Built for the Keep."
DISCORD_URL="https://discord.gg/cZDeqECzX"
SPEC_URL="https://otaconskeep.github.io/expansion/"

REPO_URL="https://github.com/Otaconskeep/otacons-ai-ecosystem.git"
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
VENV_DIR="$INSTALL_DIR/.venv"
DATA_DIR="${OTACON_EXPANSION_DATA_DIR:-$HOME/.config/otacon/expansion/agents}"
RUN_TESTS="${OTACON_RUN_TESTS:-1}"

REQUIRED_FAIL=0
TESTS_OK=0
TESTS_SKIPPED=0
SEED_OK=0

INSTALL_LOG_DIR="${OTACON_INSTALL_LOG_DIR:-$HOME/.config/otacon/logs}"
mkdir -p "$INSTALL_LOG_DIR"
INSTALL_LOG="$INSTALL_LOG_DIR/install-expansion-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$INSTALL_LOG") 2>&1

log()  { printf '\n\033[1;36m[AGG::EXPANSION]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[AGG::OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[AGG::WARN]\033[0m %s\n' "$*" >&2; }
die()  {
  printf '\033[1;31m[AGG::FAIL]\033[0m %s\n' "$*" >&2
  printf '\033[1;31m[AGG::FAIL]\033[0m Failed stage near line %s. Log: %s\n' "${BASH_LINENO[0]:-$LINENO}" "$INSTALL_LOG" >&2
  exit 1
}
trap 'printf "\n\033[1;31m[AGG::FAIL]\033[0m Installer stopped on line %s. Log: %s\n" "$LINENO" "$INSTALL_LOG" >&2' ERR
log "Install log -> $INSTALL_LOG"

printf '\033[1;35m'
cat <<'EXPANSION_ASCII'
==============================================================================
              O T A C O N   E X P A N S I O N
                  foundation layer install
==============================================================================
                       ANTONIO G. GARCIA
                       Built for the Keep.
==============================================================================
EXPANSION_ASCII
printf '\033[0m\n'
printf '\033[1;36m%s\033[0m\n' "$BRAND"
printf '\033[0;37m%s :: %s\033[0m\n' "$PRODUCT" "$TAGLINE"
printf '\033[0;33mThis installs the canonical schema, formulas, and a validated 5-agent\033[0m\n'
printf '\033[0;33mdefault roster. Foundation install is verified; entitled UI surfaces need\033[0m\n'
printf '\033[0;33mentitlement + Core restart. Optional Discord/HA/n8n stay unconfigured until set up.\033[0m\n'
printf '\033[0;37mFull spec & status: %s\033[0m\n\n' "$SPEC_URL"

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ------------------------------------------------------------------------------
# Discover Core install (dynamic — no hardcoded usernames/paths)
# ------------------------------------------------------------------------------
discover_core_root() {
  if [[ -n "${OTACON_INSTALL_DIR:-}" && -d "${OTACON_INSTALL_DIR}/.git" && -d "${OTACON_INSTALL_DIR}/core" ]]; then
    printf '%s\n' "$OTACON_INSTALL_DIR"
    return 0
  fi
  local home u
  while IFS=: read -r u _x _uid _gid _gecos home _shell; do
    case "$home" in ""|"/"|"/nonexistent") continue ;; esac
    if [[ -d "$home/otacon-ai-ecosystem/.git" && -d "$home/otacon-ai-ecosystem/core" ]]; then
      printf '%s\n' "$home/otacon-ai-ecosystem"
      return 0
    fi
  done <<EOF
$(getent passwd)
EOF
  if [[ -d /root/otacon-ai-ecosystem/.git && -d /root/otacon-ai-ecosystem/core ]]; then
    printf '%s\n' /root/otacon-ai-ecosystem
    return 0
  fi
  return 1
}

resolve_owner() {
  local root="$1"
  local owner
  owner="$(stat -c '%U' "$root" 2>/dev/null || true)"
  if [[ -z "$owner" ]] || ! id -u "$owner" >/dev/null 2>&1; then
    return 1
  fi
  printf '%s\n' "$owner"
}

run_as_owner() {
  # Usage: run_as_owner OWNER -- command...
  local owner="$1"
  shift
  if [[ "$1" == "--" ]]; then shift; fi
  if [[ "$owner" == "root" ]] || [[ "$(id -u)" != "0" ]]; then
    "$@"
  else
    runuser -u "$owner" -- "$@"
  fi
}

# ------------------------------------------------------------------------------
# Core prerequisite
# ------------------------------------------------------------------------------
log "Checking for an existing Otacon Core install"

DISCOVERED="$(discover_core_root || true)"
if [[ -z "$DISCOVERED" ]]; then
  die "Otacon Core is not installed (no otacon-ai-ecosystem with core/ found). Expansion installs on top of Core -- install Core first:
    curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh | bash
  Then rerun this script. (If Core is elsewhere, set OTACON_INSTALL_DIR to that path first.)"
fi
INSTALL_DIR="$DISCOVERED"
VENV_DIR="$INSTALL_DIR/.venv"
OWNER="$(resolve_owner "$INSTALL_DIR" || true)"
if [[ -z "$OWNER" ]]; then
  die "Could not resolve repository owner for $INSTALL_DIR"
fi
OWNER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"
if [[ -z "$OWNER_HOME" || ! -d "$OWNER_HOME" ]]; then
  die "Owner home missing for $OWNER"
fi
# Prefer owner-scoped expansion data unless caller overrode.
if [[ -z "${OTACON_EXPANSION_DATA_DIR:-}" ]]; then
  DATA_DIR="$OWNER_HOME/.config/otacon/expansion/agents"
else
  DATA_DIR="$OTACON_EXPANSION_DATA_DIR"
fi
if [[ -z "${OTACON_INSTALL_LOG_DIR:-}" ]]; then
  INSTALL_LOG_DIR="$OWNER_HOME/.config/otacon/logs"
else
  INSTALL_LOG_DIR="$OTACON_INSTALL_LOG_DIR"
fi
mkdir -p "$INSTALL_LOG_DIR"
# Re-bind log if we discovered a better owner home after early tee setup
if [[ "$INSTALL_LOG" != "$INSTALL_LOG_DIR/"* ]]; then
  NEW_LOG="$INSTALL_LOG_DIR/install-expansion-$(date +%Y%m%d-%H%M%S).log"
  cp -f "$INSTALL_LOG" "$NEW_LOG" 2>/dev/null || true
  INSTALL_LOG="$NEW_LOG"
fi

ok "Otacon Core found: $INSTALL_DIR (owner=$OWNER)"
echo "EXP_CORE_ROOT=$INSTALL_DIR"
echo "EXP_CORE_OWNER=$OWNER"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  die "Core's Python virtual environment wasn't found at $VENV_DIR/bin/python. Re-run Core's installer to repair it, then rerun this script."
fi
VPY="$VENV_DIR/bin/python"
ok "Reusing Core's Python environment: $VPY"

# ------------------------------------------------------------------------------
# WSL/Linux network preflight (Windows downloads ≠ WSL routes)
# ------------------------------------------------------------------------------
log "Checking WSL/Linux reachability to GitHub before repo sync"
_wsl_net_ok=0
if command_exists getent && getent hosts github.com >/dev/null 2>&1; then
  _wsl_net_ok=1
elif command_exists curl && curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1; then
  _wsl_net_ok=1
elif command_exists git && git ls-remote --heads "$REPO_URL" HEAD >/dev/null 2>&1; then
  _wsl_net_ok=1
fi
if [[ "$_wsl_net_ok" != "1" ]]; then
  echo "EXP_FAIL=wsl_network"
  echo "EXP_FAIL_DETAIL=cannot_resolve_github"
  printf '\n'
  printf ' ################################################################\n'
  printf ' #  !!!  ACTION REQUIRED - NETWORK  !!!\n'
  printf ' #  WSL CANNOT REACH GITHUB (WINDOWS MAY STILL WORK)\n'
  printf ' ################################################################\n'
  printf '     Windows downloads and WSL networking are SEPARATE stacks.\n'
  printf '     YOU MUST: fix WSL DNS/default route / VPN / .wslconfig, then:\n'
  printf '       wsl --shutdown\n'
  printf '       ping -c2 github.com   (inside Ubuntu)\n'
  printf '     Then re-run Expansion Setup.\n'
  printf '     Guide: %%LOCALAPPDATA%%\\OtaconsKeep\\TROUBLESHOOTING.txt section 2\n'
  printf ' ################################################################\n'
  printf '\n'
  die "WSL/Linux cannot reach github.com (no DNS/default route). Windows may still download fine — these are separate stacks. Fix WSL networking (default route / .wslconfig / VPN adapters), then rerun Expansion. Log: $INSTALL_LOG"
fi
ok "WSL/Linux can resolve github.com"

# ------------------------------------------------------------------------------
# Repository sync (same repo Core already cloned -- expansion/ lives inside it)
# ------------------------------------------------------------------------------
log "Synchronizing the public repository"

if ! run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" fetch --prune origin; then
  _git_ec=$?
  echo "EXP_FAIL=git_fetch"
  echo "EXP_FAIL_DETAIL=exit_${_git_ec}"
  die "git fetch failed (exit ${_git_ec}). Usually WSL DNS/routing or GitHub unreachable — not a missing Lite install. Log: $INSTALL_LOG"
fi
CURRENT_BRANCH="$(run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" branch --show-current || true)"
# Match Core installer: diverged trees (ahead/behind) must not die on exit 128.
# Prefer release.json.commit from origin/main (strict pin); else origin/main tip.
if [[ "$CURRENT_BRANCH" == "main" || -z "$CURRENT_BRANCH" ]]; then
  if ! run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" pull --ff-only; then
    BACKUP_REF="backup/pre-expansion-$(date +%Y%m%d-%H%M%S)"
    warn "Fast-forward pull failed (local tip diverged from origin/main)."
    warn "Saving local tip as ${BACKUP_REF}, then resetting to release pin / origin/main."
    run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" branch "$BACKUP_REF" HEAD || true
  fi
  RELEASE_PIN="$(
    run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" show origin/main:release.json 2>/dev/null \
      | python3 -c 'import sys,json; print((json.load(sys.stdin).get("commit") or "").strip())' 2>/dev/null \
      || true
  )"
  ORIGIN_TIP="$(run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" rev-parse origin/main 2>/dev/null || true)"
  SYNC_TARGET="origin/main"
  if [[ -n "${RELEASE_PIN:-}" ]] && run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" cat-file -e "${RELEASE_PIN}^{commit}" 2>/dev/null; then
    SYNC_TARGET="$RELEASE_PIN"
    log "Soft-update feature pin (release.json.commit)=${RELEASE_PIN}"
    if [[ -n "${ORIGIN_TIP:-}" && "${ORIGIN_TIP}" != "${RELEASE_PIN}" ]]; then
      log "origin/main tip=${ORIGIN_TIP} (often a chore(release) that only refreshes the pin — not the install target)"
    fi
  else
    warn "No usable release.json.commit — Expansion sync → origin/main"
  fi
  run_as_owner "$OWNER" -- git -C "$INSTALL_DIR" reset --hard "$SYNC_TARGET"
  ok "Working tree matches feature pin ${SYNC_TARGET}."
else
  warn "Repository is on branch '${CURRENT_BRANCH:-detached}'. Fetched origin only; leaving your branch untouched."
fi

if [[ ! -d "$INSTALL_DIR/expansion" ]]; then
  die "expansion/ was not found in $INSTALL_DIR after syncing. Your Core checkout may predate Expansion; try: git -C \"$INSTALL_DIR\" fetch --prune origin && git -C \"$INSTALL_DIR\" reset --hard origin/main, then rerun this script."
fi
ok "expansion/ present: $INSTALL_DIR/expansion"

cd "$INSTALL_DIR"

# Export for nested Python / seed so layout resolves under the owner.
export OTACON_INSTALL_DIR="$INSTALL_DIR"
export OTACON_EXPANSION_DATA_DIR="$DATA_DIR"
export HOME="$OWNER_HOME"
export OTACON_EXPANSION_CONFIG_ROOT="${OTACON_EXPANSION_CONFIG_ROOT:-$OWNER_HOME/.config/otacon/expansion}"
export OTACON_EXPANSION_DATA_ROOT="${OTACON_EXPANSION_DATA_ROOT:-$OWNER_HOME/.local/share/otacon/expansion}"

# ------------------------------------------------------------------------------
# Acceptance gate: the real expansion/ test suite
# ------------------------------------------------------------------------------
if [[ "$RUN_TESTS" == "1" ]]; then
  log "Running the Expansion test suite (foundation + P0 platform primitives)"
  if run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" PYTHONPATH="$INSTALL_DIR" \
      OTACON_EXPANSION_DATA_DIR="$DATA_DIR" \
      OTACON_EXPANSION_CONFIG_ROOT="$OTACON_EXPANSION_CONFIG_ROOT" \
      OTACON_EXPANSION_DATA_ROOT="$OTACON_EXPANSION_DATA_ROOT" \
      "$VPY" -m unittest discover -s tests -p "test_expansion_*.py" -v; then
    ok "Expansion test suite passed"
    TESTS_OK=1
  else
    warn "Expansion test suite did not fully pass -- see log above"
    TESTS_OK=0
  fi
else
  warn "Skipping the acceptance gate (OTACON_RUN_TESTS=0) -- Windows installer verifies via foundation + API"
  TESTS_OK=0
  TESTS_SKIPPED=1
fi

# ------------------------------------------------------------------------------
# Seed the five default agents (schema-validated, hierarchy-validated)
# ------------------------------------------------------------------------------
log "Generating and validating the default roster (Aria, Vector, Ledger, Muse, Sentry)"

if run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" PYTHONPATH="$INSTALL_DIR" \
    OTACON_EXPANSION_DATA_DIR="$DATA_DIR" \
    "$VPY" -m expansion.seed_defaults "$DATA_DIR"; then
  ok "Default roster written to $DATA_DIR"
  SEED_OK=1
else
  warn "Default roster generation failed validation -- see log above"
  REQUIRED_FAIL=1
fi

# ------------------------------------------------------------------------------
# P0 platform: user-state layout, versions ledger, baseline migration, readiness
# ------------------------------------------------------------------------------
log "Applying P0/P1 platform bootstrap (state layout, versions, migrations, runtime state, readiness)"
BOOT_PY="$(mktemp /tmp/otacon-expansion-bootstrap.XXXXXX.py)"
cat >"$BOOT_PY" <<'PY'
from expansion.state_layout import resolve_layout
from expansion.versions import current_versions, save_installed_versions
from expansion.migrations import apply_pending
from expansion.readiness import evaluate_foundation
from expansion.topology import default_topology, save_topology
from expansion.manifest import build_dev_manifest, save_manifest
from expansion.bootstrap import bootstrap_runtime_state
from expansion.entitlement import EntitlementGate

layout = resolve_layout()
layout.ensure_user_dirs()
save_installed_versions(current_versions())
save_topology(default_topology())
apply_pending(layout)
manifest_path = layout.user_config_root / 'PACKAGE_MANIFEST.dev.json'
save_manifest(build_dev_manifest(), manifest_path)
print('bootstrap', bootstrap_runtime_state(layout))
ent = EntitlementGate(layout).refresh_after_provision()
print('entitlement', ent.expansion_entitled, ent.source)
try:
    from expansion.capabilities.comfy_submit import migrate_stuck_creative_jobs
    print('migrate_creative', migrate_stuck_creative_jobs(layout=layout))
except Exception as exc:
    print('migrate_creative_skip', str(exc)[:200])
try:
    from expansion.release_info import release_identity
    print('release', release_identity())
except Exception as exc:
    print('release_skip', str(exc)[:200])
report = evaluate_foundation(layout)
print('foundation_ready=', report.foundation_ready())
print('surfaces_ready=', report.surfaces_ready())
print('expansion_ready=', report.expansion_ready())
print('semantic=', {k: (v.value if hasattr(v, 'value') else v) for k, v in report.semantic.items()})
if not report.foundation_ready():
    raise SystemExit(1)
PY
# Feed bootstrap via stdin so a root-owned mode-0600 temp file remains readable
# when Python runs as the non-root owner (open-by-caller, not by the child).
if run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" PYTHONPATH="$INSTALL_DIR" \
    OTACON_EXPANSION_DATA_DIR="$DATA_DIR" \
    OTACON_EXPANSION_CONFIG_ROOT="$OTACON_EXPANSION_CONFIG_ROOT" \
    OTACON_EXPANSION_DATA_ROOT="$OTACON_EXPANSION_DATA_ROOT" \
    "$VPY" - < "$BOOT_PY"
then
  ok "P0/P1 platform bootstrap complete"
  echo "EXP_FOUNDATION_READY=1"
else
  warn "P0/P1 platform bootstrap reported a problem"
  REQUIRED_FAIL=1
  echo "EXP_FOUNDATION_READY=0"
fi
rm -f "$BOOT_PY"

# Restart Core service so /api/expansion/status sees the new roster (root only).
if [[ "$(id -u)" == "0" ]] && command_exists systemctl; then
  UNIT=/etc/systemd/system/otacon.service
  if [[ -f "$UNIT" ]]; then
    log "Ensuring otacon.service PATH includes WSL nvidia-smi + Docker Desktop CLI"
    WANT_PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib:/snap/bin:/mnt/c/Program Files/Docker/Docker/resources/bin:/mnt/c/ProgramData/DockerDesktop/version-bin'
    sed -i '/^Environment=PATH=/d' "$UNIT"
    sed -i '/^Environment="PATH=/d' "$UNIT"
    sed -i "/\[Service\]/a Environment=\"PATH=${WANT_PATH}\"" "$UNIT"
    sed -i '/^Environment=LD_LIBRARY_PATH=/d' "$UNIT"
    sed -i "/\[Service\]/a Environment=LD_LIBRARY_PATH=/usr/lib/wsl/lib" "$UNIT"
    systemctl daemon-reload 2>/dev/null || true
  fi
  log "Restarting otacon.service so Expansion APIs reload"
  systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
  # Brand endpoint often answers before Expansion status finishes loading — wait for active + settle.
  for _i in 1 2 3 4 5 6 7 8 9 10; do
    st="$(systemctl is-active otacon.service 2>/dev/null || echo unknown)"
    if [[ "$st" == "active" ]]; then
      break
    fi
    sleep 1
  done
  sleep 3
  echo "EXP_SERVICE_ACTIVE=$(systemctl is-active otacon.service 2>/dev/null || echo unknown)"
fi

# Agent count proof for Windows parsers
AGENT_COUNT=0
if [[ -d "$DATA_DIR" ]]; then
  AGENT_COUNT="$(find "$DATA_DIR" -maxdepth 1 -name 'default-*.json' 2>/dev/null | wc -l | tr -d ' ')"
fi
echo "EXP_AGENT_COUNT=$AGENT_COUNT"
echo "EXP_DATA_DIR=$DATA_DIR"

# ------------------------------------------------------------------------------
# Genome Voice Trainer — Expansion premium (GPU). Install + ensure UI on :8765.
# Skip: OTACON_INSTALL_VOICE_TRAINER=0
# ------------------------------------------------------------------------------
# WSL systemd / stripped PATH often hides nvidia-smi under /usr/lib/wsl/lib —
# bare `command -v nvidia-smi` falsely skips Genome on GPU hosts (EXP_GENOME_STATE=no_gpu).
resolve_nvidia_smi() {
  if command -v nvidia-smi >/dev/null 2>&1; then command -v nvidia-smi; return 0; fi
  local p
  for p in /usr/lib/wsl/lib/nvidia-smi /usr/bin/nvidia-smi /usr/local/bin/nvidia-smi; do
    if [[ -x "$p" ]]; then printf '%s\n' "$p"; return 0; fi
  done
  return 1
}
nvidia_usable() {
  local smi
  smi="$(resolve_nvidia_smi)" || return 1
  PATH="/usr/lib/wsl/lib:/usr/bin:/bin:${PATH:-}" \
    LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$smi" >/dev/null 2>&1
}

INSTALL_VOICE_TRAINER="${OTACON_INSTALL_VOICE_TRAINER:-1}"
VOICE_TRAINER_INSTALLER_URL="${OTACON_VOICE_TRAINER_URL:-https://raw.githubusercontent.com/Otaconskeep/otacon-voice-trainer/main/install_voice_trainer.sh}"
VT_HOME="${OTACON_VT_DIR:-$OWNER_HOME/otacon-voice-trainer}"
EXP_GENOME_STATE=skipped
if [[ "$INSTALL_VOICE_TRAINER" != "1" ]]; then
  warn "Genome Voice Trainer skipped (OTACON_INSTALL_VOICE_TRAINER=0)."
  EXP_GENOME_STATE=skipped_env
elif ! nvidia_usable; then
  warn "Genome Voice Trainer (Expansion premium) needs NVIDIA GPU — nvidia-smi not usable here."
  warn "  Piper TTS still works on CPU. On a GPU host re-run Expansion or: curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash"
  warn "  Tip: Fix-Otacon-GPU.bat if Windows has a GPU but WSL nvidia-smi fails."
  EXP_GENOME_STATE=no_gpu
else
  log "Expansion premium: ensuring Genome Voice Trainer (GPU Piper via $(resolve_nvidia_smi))"
  if [[ -d "$VT_HOME" ]] && docker image inspect piper-voice-trainer:gpu >/dev/null 2>&1; then
    ok "Genome already present at $VT_HOME"
    EXP_GENOME_STATE=present
  elif [[ "$(id -u)" == "0" ]]; then
    # MUST run as root — install_voice_trainer.sh dies without TTY/sudo -n when run as owner.
    # Stage into the owner's home, then chown so Genome UI runs as the normal user.
    if env HOME="$OWNER_HOME" OTACON_VT_DIR="$VT_HOME" OTACON_VT_SKIP_UI=1 \
        PATH="/usr/lib/wsl/lib:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
        LD_LIBRARY_PATH="/usr/lib/wsl/lib" \
        bash -c "curl -fsSL \"$VOICE_TRAINER_INSTALLER_URL\" | bash"
    then
      chown -R "$OWNER":"$OWNER" "$VT_HOME" 2>/dev/null || true
      usermod -aG docker "$OWNER" 2>/dev/null || true
      ok "Genome Voice Trainer installed for Expansion (privileged → $VT_HOME)"
      EXP_GENOME_STATE=installed
    else
      warn "Genome Voice Trainer install failed — Expansion foundation continues; retry Voice Trainer later."
      EXP_GENOME_STATE=fail
    fi
  else
    # Non-root Expansion: escalate via wsl.exe -u root when on WSL (no password TTY).
    # Write a script — never bash -lc with $PATH (Windows "Program Files (x86)" breaks parentheses).
    if command -v wsl.exe >/dev/null 2>&1 || [[ -x /mnt/c/Windows/System32/wsl.exe ]]; then
      WSL_BIN="$(command -v wsl.exe 2>/dev/null || echo /mnt/c/Windows/System32/wsl.exe)"
      WSL_ARGS=()
      [[ -n "${WSL_DISTRO_NAME:-}" ]] && WSL_ARGS+=(-d "$WSL_DISTRO_NAME")
      GENOME_SH="/tmp/otacon-genome-install-$$.sh"
      cat > "$GENOME_SH" <<GEOF
#!/usr/bin/env bash
set -uo pipefail
export PATH=/usr/lib/wsl/lib:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/lib/wsl/lib
export HOME=$(printf %q "$OWNER_HOME")
export OTACON_VT_DIR=$(printf %q "$VT_HOME")
export OTACON_VT_SKIP_UI=1
export OTACON_VT_OWNER=$(printf %q "$OWNER")
export DEBIAN_FRONTEND=noninteractive
mkdir -p $(printf %q "$VT_HOME")
chown -R $(printf %q "$OWNER"):$(printf %q "$OWNER") $(printf %q "$(dirname "$VT_HOME")") 2>/dev/null || true
set +e
curl -fsSL "$VOICE_TRAINER_INSTALLER_URL" | bash
rc=\$?
set -e
chown -R $(printf %q "$OWNER"):$(printf %q "$OWNER") $(printf %q "$VT_HOME") 2>/dev/null || true
usermod -aG docker $(printf %q "$OWNER") 2>/dev/null || true
exit \$rc
GEOF
      chmod 755 "$GENOME_SH"
      if "$WSL_BIN" "${WSL_ARGS[@]}" -u root -- bash "$GENOME_SH"; then
        ok "Genome Voice Trainer installed via wsl.exe -u root"
        EXP_GENOME_STATE=installed
      else
        warn "Genome install via wsl -u root failed — re-run OtaconExpansion-Setup.bat or: wsl -u root -- bash -lc 'curl -fsSL $VOICE_TRAINER_INSTALLER_URL | bash'"
        EXP_GENOME_STATE=fail
      fi
      rm -f "$GENOME_SH" 2>/dev/null || true
    else
      warn "Genome install needs root/docker — run Expansion via Windows Setup (privileged) or: wsl -u root"
      EXP_GENOME_STATE=needs_root
    fi
  fi
  # Always write/repair status.json and verify / + status.json (never READY on port alone).
  if [[ -d "$VT_HOME" ]]; then
    log "Ensuring Genome UI + status.json under $VT_HOME"
    run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" OTACON_VT_DIR="$VT_HOME" PYTHONPATH="$INSTALL_DIR" \
      "$VPY" -c "from expansion.capabilities.voice_trainer import ensure_voice_trainer_ui; import json; print(json.dumps(ensure_voice_trainer_ui()))" \
      || true
    if (echo >/dev/tcp/127.0.0.1/8765) >/dev/null 2>&1; then
      if curl -fsS "http://127.0.0.1:8765/status.json" >/dev/null 2>&1; then
        ok "Genome UI READY on http://127.0.0.1:8765/ (status.json ok)"
        EXP_GENOME_STATE=ready
      else
        warn "Genome listens on :8765 but status.json check failed — Start Genome from Expansion to repair"
      fi
    fi
  fi
fi
echo "EXP_GENOME_STATE=$EXP_GENOME_STATE"

# ------------------------------------------------------------------------------
# Video Studio hardware profile (VRAM-first → RAM → GPU gen)
# Persists studio_hardware_profile.json + bootstrap-hardware.env Studio keys.
# Actual Comfy provision still runs from Expansion UI "Set Up Video Studio".
# ------------------------------------------------------------------------------
EXP_STUDIO_PROFILE=unknown
if [[ -n "${VPY:-}" ]] && [[ -f "$INSTALL_DIR/core/hardware_profile.py" ]]; then
  log "Video Studio profile (Z-Image / Wan·LTX-2 / ACE-Step)"
  STUDIO_OUT="$(
    run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" PYTHONPATH="$INSTALL_DIR" \
      "$VPY" -c "from core.hardware_profile import detect_studio_profile, persist_studio_profile, profile_asset_manifest; p=detect_studio_profile(); persist_studio_profile(p); print(p.profile_id); print(p.comfy_runtime); print(int(p.auto_install_studio)); print(','.join(a['id'] for a in profile_asset_manifest(p)))" \
      2>/dev/null || true
  )"
  EXP_STUDIO_PROFILE="$(printf '%s\n' "$STUDIO_OUT" | sed -n '1p')"
  EXP_STUDIO_COMFY="$(printf '%s\n' "$STUDIO_OUT" | sed -n '2p')"
  EXP_STUDIO_AUTO="$(printf '%s\n' "$STUDIO_OUT" | sed -n '3p')"
  EXP_STUDIO_ASSETS="$(printf '%s\n' "$STUDIO_OUT" | sed -n '4p')"
  ok "Studio profile=${EXP_STUDIO_PROFILE:-?} comfy=${EXP_STUDIO_COMFY:-?} auto=${EXP_STUDIO_AUTO:-?} assets=${EXP_STUDIO_ASSETS:-none}"
  case "${EXP_STUDIO_PROFILE:-}" in
    *LTX2*|*24GB*|*32GB*)
      _free_gb="$(df -Pk "$OWNER_HOME" 2>/dev/null | awk 'NR==2{printf "%.0f", $4/1024/1024}')"
      if [[ -n "${_free_gb:-}" ]] && [[ "$_free_gb" -lt 100 ]]; then
        printf '\n'
        printf ' ################################################################\n'
        printf ' #  !!!  ACTION REQUIRED - DISK  !!!\n'
        printf ' #  LTX-2 / 24GB+ STUDIO NEEDS ~100 GB FREE\n'
        printf ' ################################################################\n'
        printf '     Free space near home: %s GB (need ~100 GB for LTX packs).\n' "$_free_gb"
        printf '     YOU MUST free space; keep models in WSL/Docker (not /mnt/c).\n'
        printf ' ################################################################\n'
        printf '\n'
        warn "Low disk for LTX-2 path — pack downloads may fail until space is freed."
      fi
      printf '\n'
      printf ' ################################################################\n'
      printf ' #  !!!  NOTE - VIDEO ENGINE  !!!\n'
      printf ' #  PROFILE SELECTED LTX-2 (24GB+ / RTX 4090 CLASS)\n'
      printf ' ################################################################\n'
      printf '     Packs may download LTX-2 while Workshop video still uses Wan\n'
      printf '     until the LTX submitter ships. If video asks for Wan packs,\n'
      printf '     update Expansion + see TROUBLESHOOTING.txt section 9.\n'
      printf ' ################################################################\n'
      printf '\n'
      ;;
  esac
  # Kick hardware-matched creative packs (Z-Image + video + music) in the background
  # when this PC is auto-install eligible. Does not wait for multi-GB downloads.
  if [[ "${EXP_STUDIO_AUTO:-0}" == "1" ]]; then
    log "Auto-starting creative pack downloads for profile assets: ${EXP_STUDIO_ASSETS:-all}"
    PACK_KICK="$(
      run_as_owner "$OWNER" -- env HOME="$OWNER_HOME" PYTHONPATH="$INSTALL_DIR" \
        "$VPY" -c "
from expansion.capabilities.studio_packs import start_pack_install, packs_status
from expansion.capabilities.studio_setup import studio_hardware_snapshot
hw = studio_hardware_snapshot()
st = packs_status(hw=hw)
needed = list(st.get('needed') or [])
if st.get('ok'):
    print('started=0 running=0 needed=none detail=already_ok')
elif st.get('running'):
    print('started=0 running=1 needed=%s' % (','.join(needed) or 'none'))
else:
    out = start_pack_install(hw=hw, which=None)
    print('started=%s running=%s needed=%s' % (out.get('started'), out.get('running'), ','.join(needed) or 'none'))
" 2>/dev/null || echo 'started=0 running=0 needed=error'
    )"
    ok "Creative pack kick: ${PACK_KICK}"
    echo "EXP_PACKS_KICK=${PACK_KICK}"
  else
    warn "Studio auto-install off for this hardware — packs stay UI-driven (Set Up Video Studio)."
    echo "EXP_PACKS_KICK=skipped_auto_off"
  fi
fi
echo "EXP_STUDIO_PROFILE=${EXP_STUDIO_PROFILE:-unknown}"

# ------------------------------------------------------------------------------
# Final summary
# ------------------------------------------------------------------------------
FINAL_STATE=READY
FINAL_RC=0
if [[ "$REQUIRED_FAIL" == "1" ]]; then
  FINAL_STATE=FAILED
  FINAL_RC=1
elif [[ "$TESTS_SKIPPED" == "1" ]]; then
  FINAL_STATE=READY
  FINAL_RC=0
elif [[ "$TESTS_OK" != "1" ]]; then
  FINAL_STATE=DEGRADED
  FINAL_RC=2
fi

printf '\n\033[1;35m'
case "$FINAL_STATE" in
  READY)
    cat <<'DONE_ASCII'
==============================================================================
         OTACON EXPANSION // FOUNDATION INSTALLED
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
DONE_ASCII
    ;;
  DEGRADED)
    cat <<'DONE_ASCII'
==============================================================================
         OTACON EXPANSION // FOUNDATION DEGRADED
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
              ROSTER WRITTEN -- TEST SUITE DID NOT FULLY PASS
DONE_ASCII
    ;;
  *)
    cat <<'DONE_ASCII'
==============================================================================
         OTACON EXPANSION // FOUNDATION INSTALL FAILED
==============================================================================
                   ANTONIO G. GARCIA // OTACONSKEEP
DONE_ASCII
    ;;
esac
printf '\033[0m'

if [[ "$TESTS_SKIPPED" == "1" ]]; then
  TEST_LABEL=SKIPPED
elif [[ "$TESTS_OK" == "1" ]]; then
  TEST_LABEL=PASS
else
  TEST_LABEL="DID NOT PASS"
fi

printf 'Final state       : %s (exit %s)\n' "$FINAL_STATE" "$FINAL_RC"
printf 'Install log       : %s\n' "$INSTALL_LOG"
printf 'Repository        : %s\n' "$INSTALL_DIR"
printf 'Test suite        : %s\n' "$TEST_LABEL"
printf 'Default roster    : %s (%s)\n' "$([[ "$SEED_OK" == "1" ]] && echo written || echo FAILED)" "$DATA_DIR"
printf '\n'
printf '\033[1;33mWhat this actually gives you right now:\033[0m\n'
printf '  - A validated, versioned, five-agent roster on disk (%s)\n' "$DATA_DIR"
printf '  - P0 platform: state layout, topology config, versions, migrations,\n'
printf '    package manifest contract, provision skeleton, event bus, readiness\n'
printf '  - Importable modules under expansion/ (schema through provision/events)\n'
printf '  - Migration contract: docs/KEEP_EXPANSION_MIGRATION.md\n'
printf '\033[1;33mFeature matrix (this install):\033[0m\n'
printf '  - Foundation roster/schema     : installed (verified by this script)\n'
printf '  - Entitled surfaces (War Room) : check /api/expansion/entitlement after restart\n'
printf '  - Optional Discord/HA/n8n      : auto-install from Ops (credentials only when required)\n'
printf '\n'
printf '\033[1;33mRecommended next (Otacon can finish these):\033[0m\n'
printf '  [ ] Discord         — Ops → Configure Discord (paste bot token once)\n'
printf '  [ ] Home Assistant  — Ops → Connect HA (URL + long-lived token once)\n'
printf '  [ ] n8n             — Ops → Install n8n (Docker; no credential for base)\n'
printf '  API: POST /api/expansion/integrations/configure  {\"component\":\"discord|home_assistant|n8n\"}\n'
printf '  - Page Builder                 : page registry metadata only (not a page factory)\n'
printf '  - Full status and roadmap      : %s\n' "$SPEC_URL"
printf '\n'
printf '[ANTONIO G. GARCIA] Rerunning this installer is safe; it re-validates and re-syncs.\n'
if [[ "$FINAL_RC" -eq 0 ]]; then
  printf '[ANTONIO G. GARCIA] Foundation installed. Confirm entitlement before calling Expansion ready: %s\n' "$DISCORD_URL"
elif [[ "$FINAL_RC" -eq 2 ]]; then
  printf '[ANTONIO G. GARCIA] Roster is valid but the test suite flagged something. Check the log: %s\n' "$INSTALL_LOG"
else
  printf '[ANTONIO G. GARCIA] Foundation install did not complete. See log: %s\n' "$INSTALL_LOG"
fi
exit "$FINAL_RC"
