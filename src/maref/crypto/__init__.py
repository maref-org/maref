"""Cryptographic primitives for MAREF compliance.

This module provides China national cryptographic algorithms (SM2/SM3/SM4-GCM)
for compliance with Chinese cryptography regulations and EAR export controls.

Note: Production implementation requires gmssl library (SM2/SM3/SM4-GCM).
Current stubs use cryptography library for interface compatibility.
"""

from __future__ import annotations

from .sm2 import SM2KeyPair, SM2Signer, SM2Verifier
from .sm3 import SM3Hasher
from .sm4_gcm import SM4GCMEncryptor

__all__ = ["SM2KeyPair", "SM2Signer", "SM2Verifier", "SM3Hasher", "SM4GCMEncryptor"]
