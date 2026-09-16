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
#   verifies exactly what exists today: the versioned agent schema, the
#   bounded relationship/mood formulas, the motion-manifest schema, decision
#   audit records, readiness state, and a schema-valid five-agent default
#   roster (Aria/Vector/Ledger/Muse/Sentry) written to disk.
#
#   It does NOT install a Dashboard, Codec, War Room, Video Studio, or any
#   other UI wired to that roster -- those surfaces are specified in
#   docs/EXPANSION.md but not yet built. Nothing here overwrites, gates, or
#   otherwise touches Otacon Core. Full status: https://otaconskeep-site.otaconskeep.workers.dev/expansion/
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
SPEC_URL="https://otaconskeep-site.otaconskeep.workers.dev/expansion/"

REPO_URL="https://github.com/Otaconskeep/otacons-ai-ecosystem.git"
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
VENV_DIR="$INSTALL_DIR/.venv"
DATA_DIR="${OTACON_EXPANSION_DATA_DIR:-$HOME/.config/otacon/expansion/agents}"
RUN_TESTS="${OTACON_RUN_TESTS:-1}"

REQUIRED_FAIL=0
TESTS_OK=0
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
printf '\033[0;33mdefault roster. Dashboard/Codec/War Room/Video Studio are NOT built yet.\033[0m\n'
printf '\033[0;37mFull spec & status: %s\033[0m\n\n' "$SPEC_URL"

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ------------------------------------------------------------------------------
# Core prerequisite
# ------------------------------------------------------------------------------
log "Checking for an existing Otacon Core install"

if [[ ! -d "$INSTALL_DIR/.git" || ! -d "$INSTALL_DIR/core" ]]; then
  die "Otacon Core is not installed at $INSTALL_DIR. Expansion installs on top of Core -- install Core first:
    curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh | bash
  Then rerun this script. (If Core is installed somewhere else, set OTACON_INSTALL_DIR to that path first.)"
fi
ok "Otacon Core found: $INSTALL_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  die "Core's Python virtual environment wasn't found at $VENV_DIR/bin/python. Re-run Core's installer to repair it, then rerun this script."
fi
VPY="$VENV_DIR/bin/python"
ok "Reusing Core's Python environment: $VPY"

# ------------------------------------------------------------------------------
# Repository sync (same repo Core already cloned -- expansion/ lives inside it)
# ------------------------------------------------------------------------------
log "Synchronizing the public repository"

git -C "$INSTALL_DIR" fetch --prune origin
CURRENT_BRANCH="$(git -C "$INSTALL_DIR" branch --show-current || true)"
if [[ "$CURRENT_BRANCH" == "main" ]]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  warn "Repository is on branch '${CURRENT_BRANCH:-detached}'. Fetched origin only; leaving your branch untouched."
fi

if [[ ! -d "$INSTALL_DIR/expansion" ]]; then
  die "expansion/ was not found in $INSTALL_DIR after syncing. Your Core checkout may predate Expansion; try: git -C \"$INSTALL_DIR\" pull --ff-only, then rerun this script."
fi
ok "expansion/ present: $INSTALL_DIR/expansion"

cd "$INSTALL_DIR"

# ------------------------------------------------------------------------------
# Acceptance gate: the real expansion/ test suite
# ------------------------------------------------------------------------------
if [[ "$RUN_TESTS" == "1" ]]; then
  log "Running the Expansion test suite (foundation + P0 platform primitives)"
  if PYTHONPATH="$INSTALL_DIR" "$VPY" -m unittest discover -s tests -p "test_expansion_*.py" -v; then
    ok "Expansion test suite passed"
    TESTS_OK=1
  else
    warn "Expansion test suite did not fully pass -- see log above"
    TESTS_OK=0
  fi
else
  warn "Skipping the acceptance gate (OTACON_RUN_TESTS=0) -- not recommended"
  TESTS_OK=1
fi

# ------------------------------------------------------------------------------
# Seed the five default agents (schema-validated, hierarchy-validated)
# ------------------------------------------------------------------------------
log "Generating and validating the default roster (Aria, Vector, Ledger, Muse, Sentry)"

if PYTHONPATH="$INSTALL_DIR" "$VPY" -m expansion.seed_defaults "$DATA_DIR"; then
  ok "Default roster written to $DATA_DIR"
  SEED_OK=1
else
  warn "Default roster generation failed validation -- see log above"
  REQUIRED_FAIL=1
fi

# ------------------------------------------------------------------------------
# P0 platform: user-state layout, versions ledger, baseline migration, readiness
# ------------------------------------------------------------------------------
log "Applying P0 platform bootstrap (state layout, versions, migrations, readiness)"
if PYTHONPATH="$INSTALL_DIR" OTACON_EXPANSION_DATA_DIR="$DATA_DIR" "$VPY" - <<'PY'
from expansion.state_layout import resolve_layout
from expansion.versions import current_versions, save_installed_versions
from expansion.migrations import apply_pending
from expansion.readiness import evaluate_foundation
from expansion.topology import default_topology, save_topology
from expansion.manifest import build_dev_manifest, save_manifest

layout = resolve_layout()
layout.ensure_user_dirs()
save_installed_versions(current_versions())
save_topology(default_topology())
apply_pending(layout)
manifest_path = layout.user_config_root / 'PACKAGE_MANIFEST.dev.json'
save_manifest(build_dev_manifest(), manifest_path)
report = evaluate_foundation(layout)
print('foundation_ready=', report.foundation_ready())
print('semantic=', {k: (v.value if hasattr(v, 'value') else v) for k, v in report.semantic.items()})
if not report.foundation_ready():
    raise SystemExit(1)
PY
then
  ok "P0 platform bootstrap complete"
else
  warn "P0 platform bootstrap reported a problem"
  REQUIRED_FAIL=1
fi

# ------------------------------------------------------------------------------
# Final summary
# ------------------------------------------------------------------------------
FINAL_STATE=READY
FINAL_RC=0
if [[ "$REQUIRED_FAIL" == "1" ]]; then
  FINAL_STATE=FAILED
  FINAL_RC=1
elif [[ "$TESTS_OK" != "1" ]]; then
  FINAL_STATE=DEGRADED
  FINAL_RC=2
fi

printf '\n\033[1;35m'
case "$FINAL_STATE" in
  READY)
    cat <<'DONE_ASCII'
==============================================================================
         OTACON EXPANSION // FOUNDATION LAYER READY
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

printf 'Final state       : %s (exit %s)\n' "$FINAL_STATE" "$FINAL_RC"
printf 'Install log       : %s\n' "$INSTALL_LOG"
printf 'Repository        : %s\n' "$INSTALL_DIR"
printf 'Test suite        : %s\n' "$([[ "$TESTS_OK" == "1" ]] && echo PASS || echo "DID NOT PASS")"
printf 'Default roster    : %s (%s)\n' "$([[ "$SEED_OK" == "1" ]] && echo written || echo FAILED)" "$DATA_DIR"
printf '\n'
printf '\033[1;33mWhat this actually gives you right now:\033[0m\n'
printf '  - A validated, versioned, five-agent roster on disk (%s)\n' "$DATA_DIR"
printf '  - P0 platform: state layout, topology config, versions, migrations,\n'
printf '    package manifest contract, provision skeleton, event bus, readiness\n'
printf '  - Importable modules under expansion/ (schema through provision/events)\n'
printf '  - Migration contract: docs/KEEP_EXPANSION_MIGRATION.md\n'
printf '\033[1;33mWhat this does NOT give you yet:\033[0m\n'
printf '  - A Dashboard, Codec, War Room, Video Studio, Page Builder UI\n'
printf '  - Discord/Home Assistant/n8n wiring, voice synthesis from the seeded agents\n'
printf '  - Full status and roadmap: %s\n' "$SPEC_URL"
printf '\n'
printf '[ANTONIO G. GARCIA] Rerunning this installer is safe; it re-validates and re-syncs.\n'
if [[ "$FINAL_RC" -eq 0 ]]; then
  printf '[ANTONIO G. GARCIA] Foundation layer verified. Questions or want early access to what'"'"'s next: %s\n' "$DISCORD_URL"
elif [[ "$FINAL_RC" -eq 2 ]]; then
  printf '[ANTONIO G. GARCIA] Roster is valid but the test suite flagged something. Check the log: %s\n' "$INSTALL_LOG"
else
  printf '[ANTONIO G. GARCIA] Foundation install did not complete. See log: %s\n' "$INSTALL_LOG"
fi
exit "$FINAL_RC"
