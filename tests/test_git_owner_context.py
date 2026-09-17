#!/usr/bin/env python3
"""Git in repair/fix-gpu must run as repo owner (not root), without safe.directory hacks."""
from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def extract_bash(ps1: str) -> str:
    """Extract first single-quoted here-string payload from a PowerShell file."""
    # Prefer the Invoke-Wsl / $bash = @' ... '@ block
    start = ps1.find("$bash = @'")
    if start < 0:
        start = ps1.find("$bash = @\"")
    if start < 0:
        return ""
    # find opening after @'
    q = ps1.find("@'", start)
    if q < 0:
        return ""
    body_start = q + 2
    if body_start < len(ps1) and ps1[body_start] == "\n":
        body_start += 1
    end = ps1.find("\n'@", body_start)
    if end < 0:
        end = ps1.find("'@", body_start)
    return ps1[body_start:end]


def write_owner_git_lib(path: Path) -> None:
    """Standalone copy of the owner-aware git helpers for live cases."""
    path.write_text(
        r'''#!/bin/bash
set +e
resolve_owner() {
  ROOT="$1"
  OWNER="$(stat -c '%U' "$ROOT" 2>/dev/null || true)"
  OWNER_UID="$(stat -c '%u' "$ROOT" 2>/dev/null || true)"
  if [ -z "$OWNER" ] || [ -z "$OWNER_UID" ]; then
    echo "FAIL owner_lookup_failed"
    return 3
  fi
  if ! id -u "$OWNER" >/dev/null 2>&1; then
    echo "FAIL owner_invalid"
    return 3
  fi
  if [ "$OWNER" = "root" ] && [ "$OWNER_UID" != "0" ]; then
    echo "FAIL owner_root_mismatch"
    return 3
  fi
  if [ "$OWNER" != "root" ] && ! command -v runuser >/dev/null 2>&1; then
    echo "FAIL runuser_missing"
    return 3
  fi
  echo "OWNER=$OWNER"
  echo "OWNER_UID=$OWNER_UID"
  return 0
}

git_as_owner() {
  ROOT="$1"; shift
  OWNER="$1"; shift
  if [ "$OWNER" = "root" ]; then
    git -C "$ROOT" "$@"
  else
    runuser -u "$OWNER" -- git -C "$ROOT" "$@"
  fi
}
''',
        encoding="utf-8",
    )


def main() -> int:
    fails: list[str] = []
    repair = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")
    fixgpu = (ROOT / "deploy" / "fix-otacon-gpu.ps1").read_text(encoding="utf-8-sig")
    bash = extract_bash(repair)
    fix_bash = extract_bash(fixgpu)

    must("git_as_owner()" in bash or "git_as_owner ()" in bash.replace(" ", ""),
         "repair defines git_as_owner", fails)
    must("runuser -u \"$OWNER\" -- git -C \"$ROOT\"" in bash
         or 'runuser -u "$OWNER" -- git -C "$ROOT"' in bash,
         "repair runs git via runuser as OWNER", fails)
    must("stat -c '%U'" in bash or 'stat -c "%U"' in bash or "stat -c '%U'" in bash.replace('"', "'"),
         "repair detects owner via stat %U", fails)
    # Accept either quoting style
    must("stat -c" in bash and "%U" in bash, "repair uses stat -c %U", fails)
    must("owner_lookup_failed" in bash, "repair fails when owner lookup fails", fails)
    must("owner_invalid" in bash, "repair validates owner exists", fails)
    must("owner_root_mismatch" in bash, "repair rejects fake root owner", fails)
    must(
        "safe.directory *" not in bash
        and "safe.directory '*'" not in bash
        and "safe.directory \"*\"" not in bash
        and "--add safe.directory" not in repair
        and "--add safe.directory" not in bash,
        "repair does not disable safe.directory",
        fails,
    )
    must("chown -R" not in bash and "chmod -R" not in bash,
         "repair does not chown/chmod the repo away", fails)
    must("unknown/query_failed" in bash, "repair reports unknown/query_failed on rev-parse fail", fails)
    must("stage=git-fetch" in bash, "repair emits stage=git-fetch", fails)
    must("stage=git-reset" in bash, "repair emits stage=git-reset", fails)
    must("git_exit=" in bash, "repair emits git_exit=", fails)
    must("stage=systemd" in bash, "repair keeps systemd stage as root", fails)
    must("systemctl" in bash, "repair still uses systemctl as root", fails)
    # Root must not call bare git -C for sync (allow definition body only via git_as_owner)
    bare_fetch = [ln for ln in bash.splitlines()
                  if "git -C \"$ROOT\" fetch" in ln or "git -C '$ROOT' fetch" in ln]
    must(len(bare_fetch) == 0, "repair has no bare root git fetch", fails)

    must("git_as_owner" in fix_bash, "fix-gpu defines/uses git_as_owner", fails)
    must("runuser -u" in fix_bash, "fix-gpu runs git via runuser", fails)
    must("safe.directory" not in fix_bash, "fix-gpu does not touch safe.directory", fails)
    must("stage=git-fetch" in fix_bash, "fix-gpu emits stage=git-fetch", fails)

    # --- Live ownership cases ---
    if os.geteuid() != 0:
        must(True, "skip live owner cases (not root)", fails)
        print("=" * 60)
        return 0 if not fails else 1

    runuser = shutil.which("runuser")
    must(runuser is not None, "runuser available for live cases", fails)
    if not runuser:
        print("=" * 60)
        return 1

    # Pick a normal user (prefer non-system)
    candidates = []
    for ent in pwd.getpwall():
        if 1000 <= ent.pw_uid < 65534 and ent.pw_name not in ("nobody",):
            candidates.append(ent.pw_name)
    if not candidates:
        # fall back
        for name in ("sduser", "ceph", "Xof", "claude"):
            try:
                pwd.getpwnam(name)
                candidates.append(name)
            except KeyError:
                pass
    must(len(candidates) > 0, "found a normal user for ownership cases", fails)
    if not candidates:
        print("=" * 60)
        return 1
    user_a = candidates[0]
    user_b = candidates[1] if len(candidates) > 1 else candidates[0]

    with tempfile.TemporaryDirectory(prefix="otacon-owner-") as td:
        td_path = Path(td)
        lib = td_path / "owner-git-lib.sh"
        write_owner_git_lib(lib)

        def sh(script: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bash", "-c", f"source '{lib}'; {script}"],
                text=True,
                capture_output=True,
            )

        # Case A: repo owned by normal user, commands as root via runuser
        repo_a = td_path / "repo-a"
        repo_a.mkdir()
        subprocess.check_call(["git", "init", "-q", str(repo_a)])
        subprocess.check_call(["git", "-C", str(repo_a), "config", "user.email", "t@t"])
        subprocess.check_call(["git", "-C", str(repo_a), "config", "user.name", "t"])
        (repo_a / "f.txt").write_text("a\n", encoding="utf-8")
        subprocess.check_call(["git", "-C", str(repo_a), "add", "f.txt"])
        subprocess.check_call(["git", "-C", str(repo_a), "commit", "-qm", "init"])
        shutil.chown(repo_a, user=user_a, group=user_a)
        # chown -R
        for dirpath, dirnames, filenames in os.walk(repo_a):
            shutil.chown(dirpath, user=user_a, group=user_a)
            for fn in filenames:
                shutil.chown(Path(dirpath) / fn, user=user_a, group=user_a)

        # Root bare git should hit dubious ownership (or at least not be our strategy)
        bare = subprocess.run(
            ["git", "-C", str(repo_a), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        # On modern git this fails with dubious ownership
        if bare.returncode != 0:
            must(
                "dubious ownership" in (bare.stderr + bare.stdout).lower()
                or bare.returncode == 128,
                "Case A: root bare git fails (dubious ownership)",
                fails,
            )
        else:
            print("WARN  Case A: this git allows root access without safe.directory; still require runuser path")

        r = sh(
            f'resolve_owner "{repo_a}"; ec=$?; echo EC=$ec; '
            f'[ $ec -eq 0 ] || exit $ec; '
            f'OWNER=$(stat -c %U "{repo_a}"); '
            f'out=$(git_as_owner "{repo_a}" "$OWNER" rev-parse HEAD); echo HEAD=$out; echo OK'
        )
        must(r.returncode == 0 and "OWNER=" + user_a in r.stdout and "HEAD=" in r.stdout,
             f"Case A: runuser as {user_a} rev-parse succeeds", fails)
        if r.returncode != 0:
            print("  stdout:", r.stdout)
            print("  stderr:", r.stderr)

        # Case B: different owner detected
        if user_b != user_a:
            repo_b = td_path / "repo-b"
            shutil.copytree(repo_a, repo_b)
            for dirpath, dirnames, filenames in os.walk(repo_b):
                shutil.chown(dirpath, user=user_b, group=user_b)
                for fn in filenames:
                    shutil.chown(Path(dirpath) / fn, user=user_b, group=user_b)
            r = sh(f'resolve_owner "{repo_b}"')
            must(r.returncode == 0 and f"OWNER={user_b}" in r.stdout,
                 f"Case B: detected owner is {user_b}", fails)
        else:
            must(True, "Case B: only one normal user - skipped distinct-owner check", fails)

        # Case C: owner lookup fails (path missing)
        r = sh('resolve_owner "/tmp/otacon-does-not-exist-xyz"')
        must(r.returncode != 0 and "owner_lookup_failed" in r.stdout,
             "Case C: missing path fails safely", fails)

        # Case D: genuinely root-owned repo - root may run git directly
        repo_d = td_path / "repo-d"
        subprocess.check_call(["git", "init", "-q", str(repo_d)])
        subprocess.check_call(["git", "-C", str(repo_d), "config", "user.email", "t@t"])
        subprocess.check_call(["git", "-C", str(repo_d), "config", "user.name", "t"])
        (repo_d / "f.txt").write_text("d\n", encoding="utf-8")
        subprocess.check_call(["git", "-C", str(repo_d), "add", "f.txt"])
        subprocess.check_call(["git", "-C", str(repo_d), "commit", "-qm", "init"])
        # already root-owned
        r = sh(
            f'resolve_owner "{repo_d}"; OWNER=$(stat -c %U "{repo_d}"); '
            f'out=$(git_as_owner "{repo_d}" "$OWNER" rev-parse HEAD); echo OWNER=$OWNER HEAD=$out'
        )
        must(r.returncode == 0 and "OWNER=root" in r.stdout and "HEAD=" in r.stdout,
             "Case D: root-owned repo allows root git", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("Git owner-context regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
