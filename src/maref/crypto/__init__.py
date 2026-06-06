"""Cryptographic primitives for MAREF compliance.

This module provides China national cryptographic algorithms (SM2/SM3/SM4-GCM)
for compliance with Chinese cryptography regulations and EAR export controls.

Note: Production implementation requires gmssl library (SM2/SM3/SM4-GCM).
Current stubs use cryptography library for interface compatibility.
"""

from __future__ import annotations

from .sm2 import SM2KeyPair, SM2Signer, SM2Verifier, sm2_decrypt, sm2_encrypt, sm2_sign, sm2_verify
from .sm3 import SM3Hasher, sm3_hash, sm3_hmac
from .sm4 import sm4_decrypt_cbc, sm4_encrypt_cbc
from .sm4_gcm import SM4GCMEncryptor, sm4_decrypt_gcm, sm4_encrypt_gcm

__all__ = [
    "SM2KeyPair", "SM2Signer", "SM2Verifier", "SM3Hasher", "SM4GCMEncryptor",
    "sm2_decrypt", "sm2_encrypt", "sm2_sign", "sm2_verify",
    "sm3_hash", "sm3_hmac",
    "sm4_decrypt_cbc", "sm4_encrypt_cbc",
    "sm4_decrypt_gcm", "sm4_encrypt_gcm",
]
