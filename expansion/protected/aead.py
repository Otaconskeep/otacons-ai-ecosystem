"""Authenticated encryption for Expansion protected bundles.

Allowed AEAD: AES-256-GCM (primary), XChaCha20-Poly1305 (reserved interface).
No custom cryptography. Bundle keys are independent high-entropy secrets —
owner passwords are never the sole package key.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AEAD_AES_256_GCM = 'AES-256-GCM'
AEAD_XCHACHA20 = 'XChaCha20-Poly1305'
NONCE_SIZE = 12  # AES-GCM standard nonce
KEY_SIZE = 32


@dataclass(frozen=True)
class EncryptedBlob:
    aead: str
    nonce: bytes
    ciphertext: bytes  # includes GCM tag
    aad: bytes = b''

    def to_wire(self) -> bytes:
        """Serialize: magic(4) | aead_len(1) | aead | nonce_len(1) | nonce | aad_len(2) | aad | ct."""
        aead_b = self.aead.encode('ascii')
        if len(aead_b) > 255 or len(self.nonce) > 255 or len(self.aad) > 65535:
            raise ValueError('field too large for wire format')
        return (
            b'OKE1'
            + bytes([len(aead_b)]) + aead_b
            + bytes([len(self.nonce)]) + self.nonce
            + len(self.aad).to_bytes(2, 'big') + self.aad
            + self.ciphertext
        )

    @staticmethod
    def from_wire(data: bytes) -> 'EncryptedBlob':
        if len(data) < 8 or data[:4] != b'OKE1':
            raise ValueError('invalid protected blob magic')
        i = 4
        alen = data[i]; i += 1
        aead = data[i:i + alen].decode('ascii'); i += alen
        nlen = data[i]; i += 1
        nonce = data[i:i + nlen]; i += nlen
        aad_len = int.from_bytes(data[i:i + 2], 'big'); i += 2
        aad = data[i:i + aad_len]; i += aad_len
        ct = data[i:]
        return EncryptedBlob(aead=aead, nonce=nonce, ciphertext=ct, aad=aad)


def generate_bundle_key() -> bytes:
    """Random independent high-entropy package key (never password-derived alone)."""
    return secrets.token_bytes(KEY_SIZE)


def encrypt_aes_gcm(plaintext: bytes, key: bytes, *, aad: bytes = b'') -> EncryptedBlob:
    if len(key) != KEY_SIZE:
        raise ValueError('AES-256-GCM requires 32-byte key')
    nonce = os.urandom(NONCE_SIZE)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad or None)
    return EncryptedBlob(aead=AEAD_AES_256_GCM, nonce=nonce, ciphertext=ct, aad=aad)


def decrypt_aes_gcm(blob: EncryptedBlob, key: bytes) -> bytes:
    if blob.aead != AEAD_AES_256_GCM:
        raise ValueError(f'unsupported aead {blob.aead}')
    if len(key) != KEY_SIZE:
        raise ValueError('AES-256-GCM requires 32-byte key')
    return AESGCM(key).decrypt(blob.nonce, blob.ciphertext, blob.aad or None)


def derive_key_argon2id(
    password: bytes,
    salt: bytes,
    *,
    time_cost: int = 3,
    memory_cost: int = 64 * 1024,
    parallelism: int = 2,
    length: int = KEY_SIZE,
) -> bytes:
    """Password-derived key (optional adjunct). Requires argon2-cffi.

    Package keys must still be independent random secrets; this may wrap
    or unlock a stored key blob — never be the sole bundle key by itself.
    """
    if not salt or len(salt) < 16:
        raise ValueError('Argon2id salt must be >= 16 random bytes')
    try:
        from argon2.low_level import Type, hash_secret_raw
    except ImportError as exc:
        raise ImportError(
            'argon2-cffi is required for password-derived keys '
            '(apt: python3-argon2 / pip: argon2-cffi)'
        ) from exc
    return hash_secret_raw(
        secret=password,
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=length,
        type=Type.ID,
    )
