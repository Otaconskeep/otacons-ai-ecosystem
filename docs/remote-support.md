# OtaconsKeep Remote Support

**Designed & Engineered by Antonio G. Garcia (Otaconskeep)**

Give a friend one customized `.bat`. They run it as Administrator. You SSH over Tailscale with your existing key. SSH is never intentionally exposed to the public internet.

```
 ============================================================
                    OTACONS KEEP
              Remote Support Bootstrap
 ------------------------------------------------------------
   Don't worry — Otacon's got your back.
 ============================================================
```

## Architecture

| Role | What |
|---|---|
| Your PC | SSH **private** key stays here only (`%USERPROFILE%\.ssh\id_ed25519`) |
| Friend PC | Tailscale + Windows OpenSSH Server + **your `.pub` only** |
| Network | Tailscale encrypted mesh; Firewall allows TCP/22 only from `100.64.0.0/10` |

Preferred:

```text
ssh Josh@otacon-josh
ssh Chris@otacon-chris
```

Fallback:

```text
ssh Josh@100.x.x.x
```

## Security rules (non-negotiable)

- Never read, copy, embed, log, or upload your SSH **private** key.
- Only `*.pub` is embedded in the friend installer.
- Tailscale auth keys are temporary, entered at build time, embedded only in the generated BAT, **never committed**.
- Do not destroy an unrelated existing Tailscale login.
- Do not disable SSH password auth until key login is proven (`Disable-SSH-PasswordAuth.ps1`).
- Do not expose SSH to `0.0.0.0/0`, do not touch the router, do not use UPnP/ZeroTier.

## Owner workflow (you)

### Josh

1. In the Tailscale admin console, create a **temporary one-off / pre-approved** auth key.
2. On your Windows PC (PowerShell):

```powershell
cd <repo>
.\tools\remote-support\Build-RemoteSupportInstaller.ps1
```

3. Enter:

- Recipient: `Josh`
- Alias: `otacon-josh` (default suggestion)
- Windows user: `Josh`
- Temporary Tailscale auth key (typed hidden)

4. Builder finds your public key automatically (`id_ed25519.pub` preferred).
5. Output (gitignored):

```text
tools/remote-support/out/OtaconsKeep-Remote-Setup-Josh.bat
```

6. Send **only that BAT** to Josh (chat/USB). It contains a temporary enrollment credential.
7. After Josh finishes, on your PC:

```powershell
tailscale status
ssh Josh@otacon-josh
```

8. When key auth works, optionally harden:

```powershell
# On Josh's PC, elevated, AFTER you confirmed key login:
.\tools\remote-support\Disable-SSH-PasswordAuth.ps1
```

9. **Delete** `OtaconsKeep-Remote-Setup-Josh.bat` after successful enrollment.

### Chris

Same steps with:

- Recipient: `Chris`
- Alias: `otacon-chris`
- Windows user: `Chris`
- Output: `OtaconsKeep-Remote-Setup-Chris.bat`
- Connect: `ssh Chris@otacon-chris`

### Owner discovery helpers

```powershell
tailscale status
tailscale ip -4 otacon-josh
```

(Use the CLI form your Tailscale version supports if `tailscale ip` differs.)

## Friend workflow (Josh / Chris only)

1. Download the file Xof sent you.
2. Right-click it.
3. Choose **Run as administrator**.
4. Click **Yes**.
5. Wait until it says **REMOTE ACCESS READY**.
6. You’re done.

No Tailscale account. No email. No browser login. No SSH setup. No IP lookup. No router changes.

## What the friend installer does

1. Elevate (or ask for Admin).
2. Install Tailscale (official MSI) if missing.
3. Enroll with the embedded one-off auth key (`--unattended`, hostname = alias).
4. Install Windows OpenSSH Server capability if missing.
5. Start `sshd` (Automatic).
6. Append your public key to `C:\ProgramData\ssh\administrators_authorized_keys` (idempotent; never overwrites others).
7. Lock ACL to SYSTEM + Administrators (SID `S-1-5-32-544`).
8. Ensure `PubkeyAuthentication yes` (password auth left alone for now).
9. Firewall rule `OtaconsKeep-SSH-Tailscale` → TCP 22 from `100.64.0.0/10` only; disable broad `OpenSSH-Server-In-TCP` Any **after** restricted rule is confirmed.
10. Validate gates; write Desktop `OtaconsKeep-Remote-Info.txt` (no secrets).
11. Log to `C:\ProgramData\OtaconsKeep\logs\remote-support-setup.log` with auth-key redaction.

## Files

| Path | Role |
|---|---|
| `tools/remote-support/Build-RemoteSupportInstaller.ps1` | Owner builder |
| `tools/remote-support/templates/RemoteSupportBootstrap.ps1` | Friend bootstrap template |
| `tools/remote-support/RemoteSupport.Common.ps1` | Shared pure helpers |
| `tools/remote-support/Disable-SSH-PasswordAuth.ps1` | Optional post-verify hardening |
| `tools/remote-support/out/*.bat` | Generated installers (**gitignored**) |
| `docs/remote-support.md` | This document |
| `tests/test_remote_support.py` | Automated safety/generation tests |
| `tests/remote_support/RemoteSupport.Tests.ps1` | Pester tests (Windows/pwsh) |

## DryRun

Friend bootstrap supports `-DryRun` (no installs/firewall/sshd changes). Useful for logic checks on a lab VM:

```bat
OtaconsKeep-Remote-Setup-Josh.bat -DryRun
```

## Acceptance matrix (manual)

| Case | Expect |
|---|---|
| A Clean Windows | Full PASS → READY |
| B Second run | Idempotent PASS, no duplicate keys/rules |
| C Tailscale installed, not enrolled | Reuse install, enroll |
| D Unrelated Tailscale connected | WARN, do not destroy, INCOMPLETE |
| E OpenSSH already installed | Reuse |
| F Existing authorized_keys | Preserve; append yours if absent |
| G Your key already present | No duplicate |
| H sshd -t fails | Restore backup; FAIL cleanly |
| I Firewall | Tailscale allowed; broad Any disabled |
| J Reboot | Tailscale unattended + sshd Automatic still reachable |

## Remaining manual steps (honest)

1. You must create the temporary Tailscale auth key in the admin console.
2. You must send the BAT to the friend through a channel you trust.
3. First SSH still uses your private key on **your** machine (never shipped).
4. Optional password-auth disable is a separate elevated script after you verify key login.
5. Full end-to-end Windows Cases A–J require a real Windows host (not fully simulated in Linux CI).
