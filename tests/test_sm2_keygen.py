"""SM2 密钥生成单元测试."""

from __future__ import annotations

import pytest

from maref.crypto.sm2 import SM2KeyPair, sm2_decrypt, sm2_encrypt, sm2_sign, sm2_verify


class TestSM2KeyGeneration:
    def test_generate_keypair_format(self) -> None:
        kp = SM2KeyPair.generate()
        # 私钥: 00 + 64 hex chars = 66 chars
        assert len(kp.private_key) == 66
        assert kp.private_key.startswith("00")
        # 公钥: 04 + 128 hex chars = 130 chars
        assert len(kp.public_key) == 130
        assert kp.public_key.startswith("04")

    def test_generate_unique_keypairs(self) -> None:
        kp1 = SM2KeyPair.generate()
        kp2 = SM2KeyPair.generate()
        assert kp1.private_key != kp2.private_key
        assert kp1.public_key != kp2.public_key

    def test_generated_keypair_encrypt_decrypt(self) -> None:
        kp = SM2KeyPair.generate()
        plaintext = b"test message for generated key"
        ciphertext = sm2_encrypt(kp.public_key, plaintext)
        decrypted = sm2_decrypt(kp.private_key, ciphertext)
        assert decrypted == plaintext

    def test_generated_keypair_sign_verify(self) -> None:
        kp = SM2KeyPair.generate()
        data = b"data to sign"
        signature = sm2_sign(kp.private_key, data, public_key=kp.public_key, use_sm3=True)
        assert sm2_verify(kp.public_key, data, signature, use_sm3=True)

    def test_generated_keypair_sign_verify_invalid(self) -> None:
        kp = SM2KeyPair.generate()
        data = b"data to sign"
        signature = sm2_sign(kp.private_key, data, public_key=kp.public_key, use_sm3=True)
        assert not sm2_verify(kp.public_key, b"tampered", signature, use_sm3=True)

    def test_keypair_immutable(self) -> None:
        kp = SM2KeyPair.generate()
        with pytest.raises(AttributeError):
            kp.private_key = "xx"  # type: ignore[misc]
