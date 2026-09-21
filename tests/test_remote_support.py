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
            # Non-interactive builder via params
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
            self.assertIn("100.64.0.0/10", payload)

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

    def test_template_has_no_real_secrets(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("{{TS_AUTH_KEY}}", t)
        self.assertIn("{{SSH_PUBKEY}}", t)
        self.assertNotRegex(t, r"tskey-auth-[A-Za-z0-9]{8,}")
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", t)
        self.assertIn("Don't worry", t)
        self.assertIn("OTACONS KEEP", t)

if __name__ == "__main__":
    unittest.main()
