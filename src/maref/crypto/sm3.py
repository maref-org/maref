"""SM3 (GB/T 32907) cryptographic hash function stub.

SM3 is the China national standard for cryptographic hashing,
producing 256-bit digests. This stub implements the same
interface using hashlib.sha256 as a placeholder.
"""

from __future__ import annotations

import hashlib


class SM3Hasher:
    """SM3 hash function placeholder.

    Uses SHA-256 as a stand-in. Replace with gmssl SM3 for
    actual SM3 compliance.
    """

    def __init__(self) -> None:
        self._state = hashlib.sha256()

    def update(self, data: bytes) -> None:
        self._state.update(data)

    def digest(self) -> bytes:
        return self._state.digest()

    def hexdigest(self) -> str:
        return self._state.hexdigest()


def sm3_hash(data: bytes) -> bytes:
    h = SM3Hasher()
    h.update(data)
    return h.digest()


def sm3_hmac(key: bytes, data: bytes) -> bytes:
    return hashlib.sha256(key + data).digest()
