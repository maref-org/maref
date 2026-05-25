"""SM4-GCM 模式单元测试."""
from __future__ import annotations

import pytest

from maref.crypto.sm4_gcm import sm4_encrypt_gcm, sm4_decrypt_gcm


SM4_KEY = b"3l5butlj26hvv313"
SM4_NONCE = b"\x00" * 12


class TestSM4GCM:
    def test_gcm_roundtrip(self) -> None:
        plaintext = b"hello sm4 gcm"
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext)
        assert len(enc.tag) == 16
        dec = sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, enc.tag)
        assert dec == plaintext

    def test_gcm_multiblock(self) -> None:
        plaintext = b"a" * 100
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext)
        dec = sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, enc.tag)
        assert dec == plaintext

    def test_gcm_with_aad(self) -> None:
        plaintext = b"secret data"
        aad = b"header info"
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext, aad=aad)
        dec = sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, enc.tag, aad=aad)
        assert dec == plaintext

    def test_gcm_tampered_ciphertext_fails(self) -> None:
        plaintext = b"important"
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext)
        tampered = bytearray(enc.ciphertext)
        tampered[0] ^= 0xFF
        with pytest.raises(ValueError, match="Authentication tag verification failed"):
            sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, bytes(tampered), enc.tag)

    def test_gcm_tampered_tag_fails(self) -> None:
        plaintext = b"important"
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext)
        bad_tag = bytearray(enc.tag)
        bad_tag[0] ^= 0xFF
        with pytest.raises(ValueError, match="Authentication tag verification failed"):
            sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, bytes(bad_tag))

    def test_gcm_wrong_aad_fails(self) -> None:
        plaintext = b"secret"
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, plaintext, aad=b"correct")
        with pytest.raises(ValueError, match="Authentication tag verification failed"):
            sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, enc.tag, aad=b"wrong")

    def test_gcm_empty_plaintext(self) -> None:
        enc = sm4_encrypt_gcm(SM4_KEY, SM4_NONCE, b"")
        dec = sm4_decrypt_gcm(SM4_KEY, SM4_NONCE, enc.ciphertext, enc.tag)
        assert dec == b""

    def test_gcm_invalid_key_length(self) -> None:
        with pytest.raises(ValueError, match="SM4 key must be 16 bytes"):
            sm4_encrypt_gcm(b"short", SM4_NONCE, b"data")

    def test_gcm_invalid_nonce_length(self) -> None:
        with pytest.raises(ValueError, match="GCM nonce must be 12 bytes"):
            sm4_encrypt_gcm(SM4_KEY, b"short", b"data")
