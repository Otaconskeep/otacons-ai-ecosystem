#!/usr/bin/env python3
"""Tester regression matrix — keep Cristo and Josh as separate cases.

CRISTO (Linux installer self-check):
  Product health GOOD; false self-check from LAN-auth globals leaking into
  concurrency HTTP tests. Fix lives in tests/http_server_isolation.py +
  test_lan_auth / test_memory_concurrency teardown. Do NOT treat as Windows
  transport.

JOSH (Windows + WSL update path):
  UPDATE FAILED mislabeled as WSL bash transport/syntax when stage exit=8.
  Exit 8 is the Linux repair script's E2E_HEALTH_FAIL — a *script* failure,
  not bash -n / temp-.sh transport. Fix: FailureClass on Invoke-OtaconWslBashFile
  + repair only sets OtaconWslTransportExit for transport|syntax.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []
    isolation = (ROOT / "tests" / "http_server_isolation.py").read_text(encoding="utf-8")
    lan = (ROOT / "tests" / "test_lan_auth_chat_modes.py").read_text(encoding="utf-8")
    conc = (ROOT / "tests" / "test_memory_concurrency.py").read_text(encoding="utf-8")
    helper = (ROOT / "deploy" / "wsl-bash-file.ps1").read_text(encoding="utf-8-sig")
    repair = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")

    # --- CRISTO ---
    must("snapshot_server_bind" in isolation and "restore_server_bind" in isolation,
         "CRISTO: bind/auth snapshot helpers exist", fails)
    must("snapshot_server_bind" in lan and "restore_server_bind" in lan,
         "CRISTO: LAN-auth tests restore BIND_MODE/LAN_TOKEN", fails)
    must("force_local_bind" in conc,
         "CRISTO: concurrency suite forces local bind", fails)

    # --- JOSH ---
    must("FailureClass" in helper,
         "JOSH: WSL transport reports FailureClass", fails)
    must("script" in helper and "syntax" in helper and "transport" in helper,
         "JOSH: FailureClass distinguishes transport|syntax|script", fails)
    must("OtaconWslScriptExit" in repair or "FailureClass" in repair,
         "JOSH: repair does not mash script exit into transport", fails)
    must("exit 8" in repair and "E2E_HEALTH_FAIL" in repair,
         "JOSH: exit 8 remains E2E health in Linux script", fails)
    # Ensure mislabel path only triggers for transport/syntax classes
    idx = repair.find("UPDATE FAILED: WSL bash file transport/syntax")
    must(idx > 0, "JOSH: transport/syntax user message still exists for true transport fails", fails)
    gate = repair[repair.find("OtaconWslTransportExit") : idx + 80] if "OtaconWslTransportExit" in repair else ""
    must("FailureClass" in repair or "syntax" in gate or "transport" in repair,
         "JOSH: transport abort is gated (not every nonzero exit)", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} tester-matrix check(s) failed")
        return 1
    print("Tester regression matrix (Cristo vs Josh): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
