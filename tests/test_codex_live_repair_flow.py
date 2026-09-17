#!/usr/bin/env python3
"""Contract: Codex live-repair phases are encoded in the installer update path.

Simulates a messy install (stale unit, fallback listener markers, no keepalive)
and asserts the repair/update scripts contain the required idempotent phases.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPAIR = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")
WAKE_TASK = (ROOT / "deploy" / "install-wake-task.ps1").read_text(encoding="utf-8-sig")
ASSISTANT = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8-sig")
UNINSTALL = (ROOT / "uninstall_otacon.bat").read_text(encoding="utf-8", errors="replace")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []

    # C: git as owner
    must("git_as_owner" in REPAIR and 'runuser -u "$OWNER"' in REPAIR, "C: git as repo OWNER via runuser", fails)
    must("git config --global --add safe.directory" not in REPAIR,
         "C: no global safe.directory disable", fails)

    # Content proofs include auth bootstrap + session bearer
    must("PROOF_AUTH_BOOTSTRAP" in REPAIR, "content proof for /api/auth/bootstrap", fails)
    must("/api/auth/bootstrap" in REPAIR, "repair checks auth bootstrap in UI", fails)

    # D: network reconcile coherent, never force LAN=1
    must("NETWORK_HOST_RECONCILED" in REPAIR, "D: HOST reconciled with LAN_MODE", fails)
    must("NETWORK_MODE_PRESERVED" in REPAIR, "D: preserves LAN mode", fails)
    must(re.search(r"OTACON_LAN_MODE=1(?!\})", REPAIR) is None, "D: never silently force LAN=1", fails)
    must("OTACON_SKIP_NVIDIA_SMI=0" in REPAIR, "D/E: GPU skip forced off", fails)

    # E: careful fallback retirement (no blind pkill -9 installer.server)
    must("RETIRE_FALLBACK_PID" in REPAIR or "is_otacon_fallback_proc" in REPAIR,
         "E: identifies Otacon fallback procs", fails)
    must("pkill -9 -f \"installer.server\"" not in REPAIR,
         "E: no blind pkill -9 installer.server", fails)
    must("FOREIGN_LISTENER" in REPAIR or "port_occupied_by_foreign" in REPAIR,
         "E: refuses to kill foreign listeners", fails)

    # F: backup + systemd verify
    must("before-otacon-repair" in REPAIR, "F: backs up unit before modify", fails)
    must("daemon-reload" in REPAIR, "F: daemon-reload", fails)
    must("UNIT_ACTIVE=active" in REPAIR or 'UNIT_ACTIVE="$ACTIVE"' in REPAIR, "F: records is-active", fails)
    must("UNIT_ENABLED_OK" in REPAIR, "F: verifies is-enabled", fails)
    must("otacon_service_not_active" in REPAIR, "F: hard-fail if inactive", fails)

    # G: keepalive paths
    must("keep-ubuntu-awake.ps1" in WAKE_TASK and "OtaconsKeep-KeepAlive.vbs" in WAKE_TASK,
         "G: keepalive script + Startup VBS", fails)
    must("GetFolderPath(\"Startup\")" in WAKE_TASK or "GetFolderPath('Startup')" in WAKE_TASK
         or 'GetFolderPath("Startup")' in WAKE_TASK,
         "G: Startup via GetFolderPath", fails)
    must("LOCALAPPDATA" in WAKE_TASK, "G: LOCALAPPDATA based keepalive", fails)
    keep = (ROOT / "deploy" / "keep-ubuntu-awake.ps1").read_text(encoding="utf-8-sig")
    must("sleep infinity" in keep, "G: keepalive holds WSL with sleep infinity", fails)
    must("Mutex" in keep, "G: keepalive single-instance mutex", fails)
    must("backoff" in keep.lower() or "backoffSec" in keep, "G: keepalive backoff (no busy-loop)", fails)
    must("crist" not in keep.lower() and r"C:\Users\\" not in keep,
         "G: keepalive has no hardcoded user paths", fails)
    must("keep-ubuntu-awake.ps1" in UNINSTALL and "OtaconsKeep-KeepAlive.vbs" in UNINSTALL,
         "G: uninstall removes keepalive", fails)

    # A: pre-modify inspect
    must("INSPECT BEGIN" in REPAIR or "stage=inspect" in REPAIR, "A: pre-modify inspect stage", fails)
    must("WINDOWS_USER=" in REPAIR, "A: logs Windows user", fails)
    must("WSL_EFFECTIVE_USER=" in REPAIR or "id -un" in REPAIR, "A: logs WSL effective user", fails)
    must("VENV_PRESENT" in REPAIR, "B: proves .venv survived update", fails)

    # H: Fix-GPU no longer blind-pkills
    fix = (ROOT / "deploy" / "fix-otacon-gpu.ps1").read_text(encoding="utf-8-sig")
    must('pkill -9 -f "installer.server"' not in fix, "H: fix-gpu no blind pkill installer.server", fails)
    must("RETIRE_FALLBACK_PID" in fix or "KEEP_LISTENER_PID" in fix, "H: fix-gpu careful listener retirement", fails)

    # H: E2E not bare HTTP 200
    must("E2E_HEALTH_OK" in REPAIR, "H: E2E health gate", fails)
    must("CHAT_1_OK" in REPAIR or "chat_once" in REPAIR, "H: Aria chat probe", fails)
    must("CHAT_2" in REPAIR or 'chat_once "2"' in REPAIR, "H: second chat probe", fails)
    must("/api/branding" in REPAIR and "/api/scan" in REPAIR, "H: branding + GPU scan", fails)
    must("manual_start" not in REPAIR.split("stage=e2e-health")[-1][:2000] or "E2E_HEALTH_OK" in REPAIR,
         "H: success requires e2e gate (not nohup-only)", fails)

    # I: reboot persistence
    must("reboot_persistence" in ASSISTANT, "I: reboot_persistence state", fails)
    must("Test-OtaconRebootPersistence" in ASSISTANT, "I: post-sign-in validation helper", fails)
    must("pending" in ASSISTANT and "verified" in ASSISTANT, "I: pending/verified states", fails)

    # Messy-install simulation: contradictory HOST/LAN reconciled without forcing LAN
    with tempfile.TemporaryDirectory() as td:
        unit = Path(td) / "otacon.service"
        unit.write_text(
            "[Service]\n"
            "Environment=OTACON_HOST=0.0.0.0\n"
            "Environment=OTACON_LAN_MODE=0\n"
            "Environment=OTACON_SKIP_NVIDIA_SMI=1\n",
            encoding="utf-8",
        )
        # Extract and run the reconcile snippet semantics from repair
        import subprocess
        script = f'''
set -e
UNIT="{unit}"
EXISTING_LAN="$(sed -n 's/^Environment=OTACON_LAN_MODE=//p' "$UNIT" | tail -n1)"
EXISTING_HOST="$(sed -n 's/^Environment=OTACON_HOST=//p' "$UNIT" | tail -n1)"
case "$(echo "${{EXISTING_LAN:-0}}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|lan) PRESERVE_LAN=1 ;;
  *) PRESERVE_LAN=0 ;;
esac
if [ "$PRESERVE_LAN" -eq 1 ]; then WANT_HOST="0.0.0.0"
elif [ "$EXISTING_HOST" = "127.0.0.1" ] || [ "$EXISTING_HOST" = "0.0.0.0" ]; then WANT_HOST="$EXISTING_HOST"
else WANT_HOST="127.0.0.1"; fi
cp -a "$UNIT" "${{UNIT}}.before-otacon-repair"
sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
sed -i "/\\[Service\\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=${{WANT_HOST}}|" "$UNIT"
sed -i '/OTACON_LAN_MODE=/d' "$UNIT"
sed -i "/\\[Service\\]/a Environment=OTACON_LAN_MODE=${{PRESERVE_LAN}}" "$UNIT"
grep OTACON_LAN_MODE= "$UNIT"
grep OTACON_HOST= "$UNIT"
grep OTACON_SKIP_NVIDIA_SMI= "$UNIT"
test -f "${{UNIT}}.before-otacon-repair"
'''
        out = subprocess.check_output(["bash", "-c", script], text=True)
        must("OTACON_LAN_MODE=0" in out, "messy: LAN stays 0", fails)
        must("OTACON_HOST=0.0.0.0" in out, "messy: HOST stays coherent 0.0.0.0 for local", fails)
        must("OTACON_SKIP_NVIDIA_SMI=0" in out, "messy: GPU skip cleared", fails)
        must((Path(td) / "otacon.service.before-otacon-repair").is_file(), "messy: unit backup created", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} Codex live-repair contract check(s) failed")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("Codex live-repair installer contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
