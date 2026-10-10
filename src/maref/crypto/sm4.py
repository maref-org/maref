"""SM4 对称加密算法封装.

基于 gmssl 的纯 Python 实现，提供与 cryptography 库风格一致的 API。
"""

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
    crypt = _sm4.CryptSM4(padding_mode=3)
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
    crypt = _sm4.CryptSM4(padding_mode=3)
    crypt.set_key(key, _sm4.SM4_DECRYPT)
    return crypt.crypt_cbc(iv, ciphertext)


class SM4GCMResult:
    def __init__(
        self, ciphertext: bytes, tag: bytes, nonce: bytes, aad: bytes | None = None
    ) -> None:
        self.ciphertext = ciphertext
        self.tag = tag
        self.nonce = nonce
        self.aad = aad


def sm4_encrypt_gcm(
    key: bytes, nonce: bytes, plaintext: bytes, aad: bytes | None = None
) -> SM4GCMResult:
    # gmssl 的 CryptSM4 不提供 GCM 模式；使用本仓库纯 Python SM4-GCM 实现
    # （sm4_gcm.py，基于 sm4_encrypt_cbc + GHASH）。延迟导入避免 sm4 与
    # sm4_gcm 的模块级循环依赖。
    from maref.crypto.sm4_gcm import sm4_encrypt_gcm as _impl

    return _impl(key, nonce, plaintext, aad or b"")


def sm4_decrypt_gcm(
    key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes | None = None
) -> bytes:
    from maref.crypto.sm4_gcm import sm4_decrypt_gcm as _impl

    return _impl(key, nonce, ciphertext, tag, aad or b"")
