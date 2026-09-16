"""Protected release subsystem: AEAD, signing, keys, bundle, verify."""
from expansion.protected.verify import VerifyResult, reject_tampered, verify_protected_package

__all__ = [
    'VerifyResult',
    'verify_protected_package',
    'reject_tampered',
]
