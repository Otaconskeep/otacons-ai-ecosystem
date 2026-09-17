#!/usr/bin/env python3
"""Static regressions: Codec THINKING cleanup + honest CHAT READY."""
from __future__ import annotations

import sys
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
    js = (ROOT / "ui" / "wizard.js").read_text(encoding="utf-8")
    srv = (ROOT / "installer" / "server.py").read_text(encoding="utf-8")
    mem = (ROOT / "core" / "memory.py").read_text(encoding="utf-8")

    # THINKING must clear via finally around sendChat request.
    must("async function sendChat()" in js, "sendChat exists", fails)
    must("setCodecMode('thinking')" in js, "thinking mode set before request", fails)
    idx_think = js.find("setCodecMode('thinking')")
    idx_finally = js.find("}finally{", idx_think)
    idx_idle = js.find("setCodecMode('idle')", idx_think)
    must(idx_finally != -1 and idx_finally < idx_idle + 200, "sendChat uses finally before/with idle cleanup", fails)
    must("I couldn't complete that request." in js, "friendly failure copy on chat error", fails)
    must("return false;" in js[js.find("function capReady"): js.find("function capReady") + 220],
         "capReady is false when capabilities missing", fails)
    must("GPU status unavailable" in js or "detection unavailable" in js, "GPU line uses scan/detection states", fails)
    must("No supported GPU detected" in js, "GPU none state has explicit copy", fails)
    must("_fallbackScan" not in js, "no fake CPU-only scan fallback after timeout", fails)
    must("GPU detection unavailable" in js, "failed scans say unavailable/retry", fails)
    must("loadHardwareScan" in js, "shared honest hardware scan helper", fails)
    must("codec-mood" in js and "refreshCodecMood" in js, "Codec mood strip wired", fails)
    must("let scan=null; // GPU sidebar line is cosmetic; skip scan" not in js,
         "Codec no longer skips /api/scan forever", fails)
    must("agent:{id:'agent_001'" not in js and "agent_id:'agent_001'" not in js,
         "wizard preview/setup no longer hardcodes agent_001", fails)
    must("PREMIUM" in js and "SETUP GENOME" in js and "SETUP STUDIO" in js,
         "Expansion entitled tiles offer Setup actions not dead PREMIUM locks", fails)
    must("KEEP ONLY" not in js and "Keep-only" not in js,
         "no Keep-only Genome framing on Expansion UI", fails)
    must('showGenomeSetup' in js and 'showVideoStudioSetup' in js and 'showComputeNodes' in js,
         "Genome/Studio/Nodes setup surfaces wired", fails)
    must('onclick="openVoiceTrainer()"' in js and 'startVoiceTrainer' in js,
         "Open/Start Genome controls wired", fails)

    must("_memory_usable" in srv and "chat_probe" in srv, "capabilities require memory + chat probe", fails)
    must("MEMORY.ping" in srv or "create_conversation('__health__'" in srv, "memory health create/list path", fails)
    must("def connection(self)" in mem and "conn.close()" in mem, "memory closes connections", fails)
    must(
        "self.db =" not in mem.replace(" ", "")
        and "self.conn=" not in mem.replace(" ", "")
        and "self.db=" not in mem.replace(" ", ""),
        "no shared self.db/self.conn assignment",
        fails,
    )

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Codec thinking / CHAT READY regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
