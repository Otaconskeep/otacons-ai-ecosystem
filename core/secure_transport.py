"""Certificate identity and authenticated transport policy (no keys in source)."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
@dataclass
class CertificateIdentity:
 fingerprint:str; subject:str; expires_at:str; revoked:bool=False
 def valid(self, trusted):
  if self.revoked or self.fingerprint not in trusted: return False
  try: return datetime.fromisoformat(self.expires_at)>datetime.now(timezone.utc)
  except ValueError: return False
class CertificateAuthority:
 def __init__(self): self.trusted={}; self.revoked=set()
 def enroll(self,subject,ttl_days=365):
  import secrets, hashlib
  f=hashlib.sha256(secrets.token_bytes(32)).hexdigest(); c=CertificateIdentity(f,subject,(datetime.now(timezone.utc)+timedelta(days=ttl_days)).isoformat(),False); self.trusted[f]=c; return c
 def revoke(self,fingerprint): self.revoked.add(fingerprint); self.trusted.get(fingerprint).revoked=True if fingerprint in self.trusted else None
 def authenticate(self,c): return c.valid(self.trusted) and c.fingerprint not in self.revoked
