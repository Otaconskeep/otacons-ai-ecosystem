"""Ed25519 signing for Expansion package manifests.

Tamper response: fail safely, preserve user data, offer repair/reinstall.
No destructive anti-tamper.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from expansion.manifest import PackageManifest, to_dict as manifest_to_dict


@dataclass
class SigningKeyPair:
    key_id: str
    private_key_pem: bytes
    public_key_pem: bytes


def generate_signing_keypair(key_id: str = 'dev-signing-1') -> SigningKeyPair:
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return SigningKeyPair(key_id=key_id, private_key_pem=priv_pem, public_key_pem=pub_pem)


def _load_private(pem: bytes) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(pem, password=None)


def _load_public(pem: bytes) -> Ed25519PublicKey:
    return serialization.load_pem_public_key(pem)


def canonical_manifest_bytes(m: PackageManifest) -> bytes:
    """Stable bytes for signing — signature/signing fields excluded."""
    d = manifest_to_dict(m)
    d.pop('signature', None)
    # signing_key_id is part of signed content (binds key identity)
    return json.dumps(d, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')


def sign_manifest(m: PackageManifest, private_pem: bytes, *, key_id: str) -> PackageManifest:
    m.signing_key_id = key_id
    payload = canonical_manifest_bytes(m)
    sig = _load_private(private_pem).sign(payload)
    m.signature = base64.b64encode(sig).decode('ascii')
    return m


def verify_manifest_signature(
    m: PackageManifest,
    public_pem: bytes,
) -> list:
    """Return error strings; empty = ok. Never deletes user data."""
    errors = []
    if not m.signature:
        return ['missing signature']
    if not m.signing_key_id:
        return ['missing signing_key_id']
    try:
        sig = base64.b64decode(m.signature)
        _load_public(public_pem).verify(sig, canonical_manifest_bytes(m))
    except Exception as exc:  # noqa: BLE001
        errors.append(f'signature verification failed: {exc}')
    return errors


def fingerprint_public_key(public_pem: bytes) -> str:
    return hashlib.sha256(public_pem).hexdigest()[:16]
