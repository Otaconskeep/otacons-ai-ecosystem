"""Safety and generation tests for OtaconsKeep remote-support bootstrap."""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RS = ROOT / "tools" / "remote-support"
COMMON = RS / "RemoteSupport.Common.ps1"
BUILDER = RS / "Build-RemoteSupportInstaller.ps1"
TEMPLATE = RS / "templates" / "RemoteSupportBootstrap.ps1"
GITIGNORE = ROOT / ".gitignore"


def _pwsh(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pwsh", "-NoProfile", "-Command", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


class RemoteSupportCommonTests(unittest.TestCase):
    def test_public_key_validation_accepts_ed25519(self):
        ps = f"""
. '{COMMON}'
$ok = Test-OtaconSshPublicKeyLine -Line 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal comment'
if (-not $ok) {{ exit 2 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_public_key_rejects_private_pem(self):
        ps = f"""
. '{COMMON}'
$ok = Test-OtaconSshPublicKeyLine -Line '-----BEGIN OPENSSH PRIVATE KEY-----'
if ($ok) {{ exit 2 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_find_rejects_opening_private_key_path(self):
        with tempfile.TemporaryDirectory() as td:
            ssh = Path(td) / ".ssh"
            ssh.mkdir()
            (ssh / "id_ed25519").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nbogus\n-----END OPENSSH PRIVATE KEY-----\n")
            (ssh / "id_ed25519.pub").write_text(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal xof@test\n"
            )
            ps = f"""
. '{COMMON}'
$p = Find-OtaconSshPublicKeyPath -HomeDir '{td}'
if ($p -notlike '*.pub') {{ Write-Host "bad:$p"; exit 2 }}
$key = Read-OtaconSshPublicKey -Path $p
if ($key -notlike 'ssh-ed25519 *') {{ exit 3 }}
try {{
  Read-OtaconSshPublicKey -Path (Join-Path '{td}' '.ssh/id_ed25519')
  exit 4
}} catch {{
  exit 0
}}
"""
            r = _pwsh(ps)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_auth_key_redaction(self):
        ps = f"""
. '{COMMON}'
$s = Protect-OtaconSecretText -Text 'up --auth-key=tskey-auth-ABC123SECRETXYZ rest' -Secrets @('tskey-auth-ABC123SECRETXYZ')
if ($s -match 'ABC123SECRETXYZ') {{ Write-Host $s; exit 2 }}
if ($s -notmatch '<REDACTED>') {{ exit 3 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_authorized_keys_idempotent(self):
        ps = f"""
. '{COMMON}'
$k = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal xof'
$a = Add-OtaconAuthorizedKeyLine -ExistingContent '' -PublicKeyLine $k
$b = Add-OtaconAuthorizedKeyLine -ExistingContent $a.Content -PublicKeyLine $k
if (-not $a.Added) {{ exit 2 }}
if ($b.Added) {{ exit 3 }}
if ($b.Count -ne 1) {{ exit 4 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_sshd_config_idempotent(self):
        ps = f"""
. '{COMMON}'
$c1 = Merge-OtaconSshdConfigLine -ConfigText "Port 22`n" -Directive 'PubkeyAuthentication' -Value 'yes'
$c2 = Merge-OtaconSshdConfigLine -ConfigText $c1 -Directive 'PubkeyAuthentication' -Value 'yes'
$n = ([regex]::Matches($c2, 'PubkeyAuthentication')).Count
if ($n -ne 1) {{ Write-Host $c2; exit 2 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_alias_normalization(self):
        ps = f"""
. '{COMMON}'
$a = ConvertTo-OtaconSafeAlias -Name 'Josh'
if ($a -ne 'otacon-josh') {{ exit 2 }}
$b = ConvertTo-OtaconSafeAlias -Name 'otacon-chris'
if ($b -ne 'otacon-chris') {{ exit 3 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_rustdesk_password_entropy_and_uniqueness(self):
        ps = f"""
. '{COMMON}'
$a = New-OtaconRustDeskPassword
$b = New-OtaconRustDeskPassword
if ($a.Length -lt 16) {{ exit 2 }}
if ($a -eq $b) {{ exit 3 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_toml_option_merge_idempotent(self):
        ps = f"""
. '{COMMON}'
$t = Merge-OtaconTomlOption -TomlText '' -Key 'direct-server' -Value 'Y'
$t = Merge-OtaconTomlOption -TomlText $t -Key 'direct-access-port' -Value '21118'
$t = Merge-OtaconTomlOption -TomlText $t -Key 'direct-server' -Value 'Y'
$n = ([regex]::Matches($t, 'direct-server')).Count
if ($n -ne 1) {{ Write-Host $t; exit 2 }}
if ($t -notmatch "direct-access-port = '21118'") {{ exit 3 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_official_rustdesk_url_gate(self):
        ps = f"""
. '{COMMON}'
$ok = Test-OtaconOfficialRustDeskUrl -Url 'https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.msi'
if (-not $ok) {{ exit 2 }}
$bad = Test-OtaconOfficialRustDeskUrl -Url 'https://mirror.example/rustdesk.msi'
if ($bad) {{ exit 3 }}
exit 0
"""
        r = _pwsh(ps)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_generated_bat_contains_pubkey_and_alias_not_private(self):
        with tempfile.TemporaryDirectory() as td:
            ssh = Path(td) / ".ssh"
            ssh.mkdir()
            pub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal xof@test"
            (ssh / "id_ed25519.pub").write_text(pub + "\n")
            (ssh / "id_ed25519").write_text(
                "-----BEGIN OPENSSH PRIVATE KEY-----\nPRIVATE_SECRET_SHOULD_NEVER_APPEAR\n-----END OPENSSH PRIVATE KEY-----\n"
            )
            out = Path(td) / "out"
            out.mkdir()
            # Point builder "here"-relative generated/ at a temp tree by copying builder... 
            # Builder writes owner file under $PSScriptRoot/generated/owner — assert gitignore instead
            # and decode BAT for RustDesk markers. Owner file path is under real repo; clean after.
            owner_dir = RS / "generated" / "owner"
            before = set(owner_dir.glob("Josh-RemoteAccess.txt")) if owner_dir.exists() else set()
            ps = f"""
$env:USERPROFILE = '{td}'
& '{BUILDER}' -Recipient 'Josh' -Alias 'otacon-josh' -SshUser 'Josh' -AuthKey 'tskey-auth-TESTONLYFAKEKEY000' -PublicKeyPath '{ssh / "id_ed25519.pub"}' -OutputDir '{out}'
"""
            r = _pwsh(ps)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            bats = list(out.glob("OtaconsKeep-Remote-Setup-Josh.bat"))
            self.assertEqual(len(bats), 1)
            raw = bats[0].read_text(encoding="utf-8", errors="replace")
            self.assertIn("___OTACON_PAYLOAD_B64_BEGIN___", raw)
            self.assertNotIn("PRIVATE_SECRET_SHOULD_NEVER_APPEAR", raw)
            self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", raw)
            m = re.search(
                r"___OTACON_PAYLOAD_B64_BEGIN___\s*([A-Za-z0-9+/=\s]+)\s*___OTACON_PAYLOAD_B64_END___",
                raw,
            )
            self.assertIsNotNone(m)
            payload = base64.b64decode(re.sub(r"\s+", "", m.group(1))).decode("utf-8")
            self.assertIn(pub, payload)
            self.assertIn("otacon-josh", payload)
            self.assertIn("tskey-auth-TESTONLYFAKEKEY000", payload)
            self.assertIn("REMOTE ACCESS READY", payload)
            self.assertIn("OtaconsKeep-SSH-Tailscale", payload)
            self.assertIn("OtaconsKeep-RustDesk-Tailscale", payload)
            self.assertIn("100.64.0.0/10", payload)
            self.assertIn("direct-server", payload)
            self.assertIn("21118", payload)
            self.assertIn("approve-mode", payload)
            self.assertNotIn("{{RUSTDESK_PASSWORD}}", payload)
            # Password embedded but Desktop info template must not print it to friend
            self.assertIn("OTACONSKEEP REMOTE SUPPORT", payload)
            self.assertIn("Remote screen support:", payload)
            self.assertNotIn("RustDesk unattended password:", payload)
            owner = RS / "generated" / "owner" / "Josh-RemoteAccess.txt"
            self.assertTrue(owner.is_file(), "owner access record must be written")
            owner_text = owner.read_text(encoding="utf-8", errors="replace")
            self.assertIn("RustDesk unattended password:", owner_text)
            self.assertIn("otacon-josh", owner_text)
            # scrub test artifact
            try:
                owner.unlink()
            except OSError:
                pass
            for leftover in (set(owner_dir.glob("Josh-RemoteAccess.txt")) - before) if owner_dir.exists() else []:
                try:
                    leftover.unlink()
                except OSError:
                    pass

    def test_josh_and_chris_get_different_rustdesk_passwords(self):
        with tempfile.TemporaryDirectory() as td:
            ssh = Path(td) / ".ssh"
            ssh.mkdir()
            pub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJustATestKeyNotReal xof@test"
            (ssh / "id_ed25519.pub").write_text(pub + "\n")
            out = Path(td) / "out"
            out.mkdir()
            for name, alias in (("Josh", "otacon-josh"), ("Chris", "otacon-chris")):
                ps = f"""
$env:USERPROFILE = '{td}'
& '{BUILDER}' -Recipient '{name}' -Alias '{alias}' -SshUser '{name}' -AuthKey 'tskey-auth-TESTONLYFAKEKEY000' -PublicKeyPath '{ssh / "id_ed25519.pub"}' -OutputDir '{out}'
"""
                r = _pwsh(ps)
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            pw = {}
            for name in ("Josh", "Chris"):
                path = RS / "generated" / "owner" / f"{name}-RemoteAccess.txt"
                self.assertTrue(path.is_file())
                text = path.read_text(encoding="utf-8")
                m = re.search(r"RustDesk unattended password:\r?\n(.+)", text)
                self.assertIsNotNone(m)
                pw[name] = m.group(1).strip()
                path.unlink(missing_ok=True)
            self.assertNotEqual(pw["Josh"], pw["Chris"])
            self.assertGreaterEqual(len(pw["Josh"]), 16)

    def test_gitignore_covers_generated_bats(self):
        text = GITIGNORE.read_text(encoding="utf-8")
        self.assertTrue(
            any(
                x in text
                for x in (
                    "OtaconsKeep-Remote-Setup-*.bat",
                    "tools/remote-support/out/",
                )
            ),
            "gitignore must exclude generated remote setup BATs",
        )
        self.assertTrue(any(x in text for x in ("generated/owner", "*-RemoteAccess.txt", "tools/remote-support/generated/")))

    def test_template_has_no_real_secrets(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("{{TS_AUTH_KEY}}", t)
        self.assertIn("{{SSH_PUBKEY}}", t)
        self.assertIn("{{RUSTDESK_PASSWORD}}", t)
        self.assertNotRegex(t, r"tskey-auth-[A-Za-z0-9]{8,}")
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", t)
        self.assertIn("Don't worry", t)
        self.assertIn("OTACONS KEEP", t)
        self.assertIn("OtaconsKeep-RustDesk-Tailscale", t)
        self.assertIn("privacy-mode", t)

    def test_owner_make_bats_exist_and_call_builder(self):
        for name in ("Make-Josh-Installer.bat", "Make-Chris-Installer.bat"):
            p = RS / name
            self.assertTrue(p.is_file(), name)
            text = p.read_text(encoding="utf-8", errors="replace")
            self.assertIn("Otacon-Make-", text)
            self.assertIn("raw.githubusercontent.com", text)
        josh_ps1 = RS / "Make-Josh.ps1"
        self.assertTrue(josh_ps1.is_file())
        jtxt = josh_ps1.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Build-RemoteSupportInstaller.ps1", jtxt)
        self.assertIn("SEND-TO-", jtxt)
        self.assertIn("CopyToDesktop", jtxt)
        chris_ps1 = RS / "Make-Chris.ps1"
        self.assertTrue(chris_ps1.is_file())
        easy = (RS / "EASY-START.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("Make-Josh.ps1", easy)
        self.assertIn("SEND-TO-JOSH.bat", easy)

if __name__ == "__main__":
    unittest.main()
