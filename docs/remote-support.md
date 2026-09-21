# OtaconsKeep Remote Support

**Designed & Engineered by Antonio G. Garcia (Otaconskeep)**

Give a friend one customized `.bat`. They run it as Administrator. You get SSH **and** full graphical remote screen control over Tailscale. Nothing is intentionally exposed to the public internet.

```
 ============================================================
                    OTACONS KEEP
              Remote Support Bootstrap
 ------------------------------------------------------------
   Don't worry — Otacon's got your back.
 ============================================================
```

## Architecture

```text
MY COMPUTER
      |
      | Tailscale private network
      |
      +----------------------+
      |                      |
      v                      v
  OpenSSH                 RustDesk
  TCP 22                  Direct IP
                          TCP 21118
      |                      |
      +----------+-----------+
                 |
                 v
             FRIEND PC
```

| Role | What |
|---|---|
| Your PC | SSH **private** key + owner access record (RustDesk password) stay here only |
| Friend PC | Tailscale + Windows OpenSSH Server + RustDesk service + **your `.pub` only** |
| Network | Tailscale mesh; firewall allows TCP/22 and TCP/21118 **only** from `100.64.0.0/10` |

Preferred:

```text
ssh Josh@otacon-josh
# RustDesk → connect to otacon-josh (or 100.x.x.x) port 21118
```

## Security rules (non-negotiable)

- Never read, copy, embed, log, or upload your SSH **private** key.
- Only `*.pub` is embedded in the friend installer.
- Tailscale auth keys are temporary, entered at build time, embedded only in the generated BAT, **never committed**.
- Each machine gets a **unique** high-entropy RustDesk unattended password (generated at build time).
- RustDesk password is written only to `tools/remote-support/generated/owner/<Name>-RemoteAccess.txt` on **your** PC — never to the friend’s Desktop info, never to general logs, never to Git.
- Do not destroy an unrelated existing Tailscale login.
- Do not disable SSH password auth until key login is proven (`Disable-SSH-PasswordAuth.ps1`).
- Do not expose SSH or RustDesk to `0.0.0.0/0`, do not touch the router, do not use UPnP/ZeroTier.
- Friend must **not** create a RustDesk account, sign in, read you an ID/password, or click Accept every session.
- This is **authorized remote technical support**, not hidden monitoring. Friend consents by running the installer.

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

4. Builder finds your public key automatically (`id_ed25519.pub` preferred) and generates a unique RustDesk password.
5. Output (gitignored):

```text
Generated:
  OtaconsKeep-Remote-Setup-Josh.bat

Owner access record:
  Josh-RemoteAccess.txt
  tools/remote-support/generated/owner/Josh-RemoteAccess.txt
```

6. Send **only the BAT** to Josh (chat/USB). Keep the owner access record private.
7. After Josh finishes, on your PC:

```powershell
tailscale status
ssh Josh@otacon-josh
```

REMOTE SCREEN: Open RustDesk → connect directly to `otacon-josh` (or fallback `100.x.x.x`) port **21118** using the password in `Josh-RemoteAccess.txt`.

8. When key auth works, optionally harden:

```powershell
# On Josh's PC, elevated, AFTER you confirmed key login:
.\tools\remote-support\Disable-SSH-PasswordAuth.ps1
```

9. **Delete** `OtaconsKeep-Remote-Setup-Josh.bat` after successful enrollment.

### Chris

Same steps with a **different** generated RustDesk password:

- Recipient: `Chris`
- Alias: `otacon-chris`
- Windows user: `Chris`
- Output BAT: `OtaconsKeep-Remote-Setup-Chris.bat`
- Owner record: `Chris-RemoteAccess.txt`
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

No Tailscale account. No email. No browser login. No SSH setup. No RustDesk account. No ID/password to read back. No IP lookup. No router changes.

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
10. Detect Windows edition and **report** native RDP host capability (AVAILABLE on Pro/Enterprise/Education; NOT AVAILABLE on Home). RDP is **not** required and TCP 3389 is **not** opened.
11. Detect RustDesk; if absent, download the current official MSI from `github.com/rustdesk/rustdesk` releases (no third-party mirrors) and silent-install.
12. Install/start RustDesk as a Windows service (Automatic) for access after reboot, before login, at the login screen (where supported), and with the UI closed.
13. Configure direct IP access (`direct-server=Y`, port `21118`), unattended permanent password, and `approve-mode=password` (no click-Accept loop).
14. Quiet / repair-friendly defaults: hide tray, privacy mode, no connection audio pop distractions; interactive UI processes are closed after service config.
15. Firewall rule `OtaconsKeep-RustDesk-Tailscale` → TCP 21118 from `100.64.0.0/10` only; disable any broad Any rules on 21118.
16. Validate gates; write Desktop `OtaconsKeep-Remote-Info.txt` (**no secrets**).
17. Log to `C:\ProgramData\OtaconsKeep\logs\remote-support-setup.log` with auth-key and RustDesk-password redaction.

## Files

| Path | Role |
|---|---|
| `tools/remote-support/Build-RemoteSupportInstaller.ps1` | Owner builder |
| `tools/remote-support/templates/RemoteSupportBootstrap.ps1` | Friend bootstrap template |
| `tools/remote-support/RemoteSupport.Common.ps1` | Shared pure helpers |
| `tools/remote-support/Disable-SSH-PasswordAuth.ps1` | Optional post-verify hardening |
| `tools/remote-support/out/*.bat` | Generated installers (**gitignored**) |
| `tools/remote-support/generated/owner/*-RemoteAccess.txt` | Owner credentials (**gitignored**) |
| `docs/remote-support.md` | This document |
| `tests/test_remote_support.py` | Automated safety/generation tests |
| `tests/remote_support/RemoteSupport.Tests.ps1` | Pester tests (Windows/pwsh) |

## DryRun

Friend bootstrap supports `-DryRun` (no installs/firewall/sshd/RustDesk changes). Useful for logic checks on a lab VM:

```bat
OtaconsKeep-Remote-Setup-Josh.bat -DryRun
```

## Acceptance matrix (manual)

| Case | Expect |
|---|---|
| A Clean Windows | Full PASS → READY (Tailscale + SSH + RustDesk) |
| B Second run | Idempotent PASS, no duplicate keys/rules; RustDesk reconfigured |
| C Tailscale installed, not enrolled | Reuse install, enroll |
| D Unrelated Tailscale connected | WARN, do not destroy, INCOMPLETE |
| E OpenSSH already installed | Reuse |
| F Existing authorized_keys | Preserve; append yours if absent |
| G Your key already present | No duplicate |
| H sshd -t fails | Restore backup; FAIL cleanly |
| I Firewall | Tailscale allowed for 22 + 21118; broad Any disabled |
| J Reboot | Tailscale unattended + sshd + RustDesk service still reachable |
| K RustDesk already installed | Reuse; apply unattended/direct config |
| L Josh vs Chris credentials | Different RustDesk passwords |
| M Secrets | Absent from Git, friend Desktop info, and redacted logs |
| N Incognito repair | Service mode + privacy-mode; friend not prompted to Accept |

## Remaining manual steps (honest)

1. You must create the temporary Tailscale auth key in the admin console.
2. You must send the BAT to the friend through a channel you trust.
3. First SSH still uses your private key on **your** machine (never shipped).
4. Graphical control uses the password in your local owner access record (never shown to the friend).
5. Optional password-auth disable is a separate elevated script after you verify key login.
6. Full end-to-end Windows Cases A–N require a real Windows host (not fully simulated in Linux CI).
