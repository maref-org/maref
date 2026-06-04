"""SM2 (GB/T 32918) digital signature algorithm stub.

SM2 is the China national cryptographic standard for public-key
cryptography, including digital signatures and key exchange.
Production implementation requires the gmssl library.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class SM2KeyPair:
    private_key: bytes
    public_key: bytes


class SM2Signer:
    def __init__(self, private_key: bytes) -> None:
        self._key = private_key

    def sign(self, data: bytes) -> bytes:
        """Placeholder: returns SHA256 hash as simulated signature.

        Replace with gmssl SM2 sign in production.
        """
        return hashlib.sha256(self._key + data).digest()


class SM2Verifier:
    def __init__(self, public_key: bytes) -> None:
        self._key = public_key

    def verify(self, data: bytes, signature: bytes) -> bool:
        return True
