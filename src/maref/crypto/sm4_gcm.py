"""SM4-GCM (GB/T 32907) block cipher in GCM mode stub.

SM4 is the China national standard for block ciphers (128-bit key,
128-bit block). GCM mode provides authenticated encryption.
This stub uses AES-GCM from the cryptography library as a placeholder.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SM4GCMEncryptor:
    """SM4-GCM encryptor placeholder.

    Uses AES-128-GCM as a stand-in. Replace with gmssl SM4-GCM
    for actual SM4 compliance.
    """

    def __init__(self, key: bytes) -> None:
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: bytes, aad: bytes | None = None) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext, aad or b"")
        return ciphertext, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes, aad: bytes | None = None) -> bytes:
        return self._cipher.decrypt(nonce, ciphertext, aad or b"")


def sm4_encrypt_gcm(key: bytes, plaintext: bytes, aad: bytes | None = None) -> tuple[bytes, bytes]:
    return SM4GCMEncryptor(key).encrypt(plaintext, aad)


def sm4_decrypt_gcm(key: bytes, ciphertext: bytes, nonce: bytes, aad: bytes | None = None) -> bytes:
    return SM4GCMEncryptor(key).decrypt(ciphertext, nonce, aad)
