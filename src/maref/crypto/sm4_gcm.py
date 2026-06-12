"""SM4 GCM 模式封装 (Galois/Counter Mode).

提供认证加密 (AEAD) 能力，满足 AIA 协议对机密性和完整性的双重要求。
基于纯 Python 实现 SM4-GCM，不依赖额外库。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

from maref.security.decorators import security_critical

from .sm4 import sm4_encrypt_cbc

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class SM4GCMResult:
    """SM4-GCM 加密结果."""

    ciphertext: bytes
    tag: bytes  # 16 字节认证标签
    nonce: bytes  # 12 字节 IV


def _sm4_ecb_encrypt_block(key: bytes, block: bytes) -> bytes:
    """SM4 ECB 单分组加密（用于 GCM 的 CTR 模式）.

    利用 CBC 模式 IV=0 的特性提取单分组加密结果。
    """
    # ECB 单分组 = CBC(iv=0, plaintext=block) xor 0 = CBC(iv=0, plaintext=block)
    zero_iv = b"\x00" * 16
    padded = block + b"\x00" * 16  # 填充到至少 32 字节避免边界问题
    cbc_out = sm4_encrypt_cbc(key, zero_iv, padded)
    # 取前 16 字节即为 ECB 加密结果
    return cbc_out[:16]


def _ghash(h: bytes, aad: bytes, ciphertext: bytes) -> bytes:
    """GCM 的 GHASH 认证函数.

    在 GF(2^128) 上进行多项式求值。
    """
    # 将 16 字节块视为 GF(2^128) 元素
    def _to_int(block: bytes) -> int:
        return int.from_bytes(block, "big")

    def _to_bytes(val: int) -> bytes:
        return val.to_bytes(16, "big")

    def _gf_mul(x: int, y: int) -> int:
        """GF(2^128) 乘法（NIST 标准）."""
        r = 0xE1000000000000000000000000000000  # 不可约多项式 x^128 + x^7 + x^2 + x + 1
        z = 0
        for i in range(128):
            if y & (1 << (127 - i)):
                z ^= x
            if x & 1:
                x = (x >> 1) ^ r
            else:
                x >>= 1
        return z

    h_val = _to_int(h)
    y = 0

    # 处理 AAD
    aad_padded = aad + b"\x00" * ((16 - len(aad) % 16) % 16)
    for i in range(0, len(aad_padded), 16):
        y = _gf_mul(y ^ _to_int(aad_padded[i:i + 16]), h_val)

    # 处理密文
    ct_padded = ciphertext + b"\x00" * ((16 - len(ciphertext) % 16) % 16)
    for i in range(0, len(ct_padded), 16):
        y = _gf_mul(y ^ _to_int(ct_padded[i:i + 16]), h_val)

    # 长度块
    len_block = struct.pack(">QQ", len(aad) * 8, len(ciphertext) * 8)
    y = _gf_mul(y ^ _to_int(len_block), h_val)

    return _to_bytes(y)


@security_critical
def sm4_encrypt_gcm(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: bytes = b"",
) -> SM4GCMResult:
    """SM4-GCM 认证加密.

    Args:
        key: 16 字节密钥
        nonce: 12 字节初始化向量
        plaintext: 待加密明文
        aad: 附加认证数据（不加密但参与认证）

    Returns:
        包含密文、认证标签和 nonce 的结果对象
    """
    if len(key) != 16:
        raise ValueError("SM4 key must be 16 bytes")
    if len(nonce) != 12:
        raise ValueError("GCM nonce must be 12 bytes")

    # 计算 H = E_K(0^128)
    h = _sm4_ecb_encrypt_block(key, b"\x00" * 16)

    # CTR 模式加密
    counter = struct.unpack(">I", nonce[8:12])[0]
    j0 = nonce + b"\x00\x00\x00\x01"

    ciphertext = bytearray()
    for i in range(0, len(plaintext), 16):
        # 计数器块 = nonce || counter
        ctr_block = nonce + struct.pack(">I", counter + (i // 16) + 1)
        keystream = _sm4_ecb_encrypt_block(key, ctr_block)
        block = plaintext[i:i + 16]
        ciphertext.extend(bytes(b ^ k for b, k in zip(block, keystream, strict=False)))

    # 计算认证标签
    s = _ghash(h, aad, bytes(ciphertext))
    j0_enc = _sm4_ecb_encrypt_block(key, j0)
    tag = bytes(a ^ b for a, b in zip(s, j0_enc, strict=False))

    return SM4GCMResult(
        ciphertext=bytes(ciphertext),
        tag=tag[:16],
        nonce=nonce,
    )


@security_critical
def sm4_decrypt_gcm(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    tag: bytes,
    aad: bytes = b"",
) -> bytes:
    """SM4-GCM 认证解密.

    Args:
        key: 16 字节密钥
        nonce: 12 字节初始化向量
        ciphertext: 密文
        tag: 16 字节认证标签
        aad: 附加认证数据

    Returns:
        解密后的明文

    Raises:
        ValueError: 认证标签验证失败（密文被篡改）
    """
    if len(key) != 16:
        raise ValueError("SM4 key must be 16 bytes")
    if len(nonce) != 12:
        raise ValueError("GCM nonce must be 12 bytes")

    # 计算 H
    h = _sm4_ecb_encrypt_block(key, b"\x00" * 16)

    # 验证标签
    s = _ghash(h, aad, ciphertext)
    j0 = nonce + b"\x00\x00\x00\x01"
    j0_enc = _sm4_ecb_encrypt_block(key, j0)
    computed_tag = bytes(a ^ b for a, b in zip(s, j0_enc, strict=False))[:16]

    if not _constant_time_compare(computed_tag, tag):
        raise ValueError("Authentication tag verification failed")

    # CTR 解密（与加密相同）
    counter = struct.unpack(">I", nonce[8:12])[0]
    plaintext = bytearray()
    for i in range(0, len(ciphertext), 16):
        ctr_block = nonce + struct.pack(">I", counter + (i // 16) + 1)
        keystream = _sm4_ecb_encrypt_block(key, ctr_block)
        block = ciphertext[i:i + 16]
        plaintext.extend(bytes(b ^ k for b, k in zip(block, keystream, strict=False)))

    return bytes(plaintext)


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """常量时间比较，防止时序攻击."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=False):
        result |= x ^ y
    return result == 0
