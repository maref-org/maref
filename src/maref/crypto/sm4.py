"""SM4 对称加密算法封装.

基于 gmssl 的纯 Python 实现，提供与 cryptography 库风格一致的 API。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gmssl import sm4 as _sm4

if TYPE_CHECKING:
    pass


def sm4_encrypt_cbc(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """SM4 CBC 模式加密.

    Args:
        key: 16 字节密钥
        iv: 16 字节初始化向量
        plaintext: 待加密明文

    Returns:
        密文（含 PKCS7 填充）
    """
    crypt = _sm4.CryptSM4(padding_mode=3)  # PKCS7
    crypt.set_key(key, _sm4.SM4_ENCRYPT)
    return crypt.crypt_cbc(iv, plaintext)


def sm4_decrypt_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """SM4 CBC 模式解密.

    Args:
        key: 16 字节密钥
        iv: 16 字节初始化向量
        ciphertext: 密文

    Returns:
        解密后的明文（自动去除 PKCS7 填充）
    """
    crypt = _sm4.CryptSM4(padding_mode=3)  # PKCS7
    crypt.set_key(key, _sm4.SM4_DECRYPT)
    return crypt.crypt_cbc(iv, ciphertext)
