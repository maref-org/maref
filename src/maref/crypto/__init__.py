"""MAREF 国密密码学模块.

提供 SM2/SM3/SM4 国密算法的统一封装，兼容 ACPs AIA 认证协议要求。
依赖: gmssl>=3.2.2
"""
from __future__ import annotations

from .sm2 import SM2KeyPair, sm2_encrypt, sm2_decrypt, sm2_sign, sm2_verify
from .sm3 import sm3_hash, sm3_hmac
from .sm4 import sm4_encrypt_cbc, sm4_decrypt_cbc
from .sm4_gcm import SM4GCMResult, sm4_encrypt_gcm, sm4_decrypt_gcm

__all__ = [
    "SM2KeyPair",
    "SM4GCMResult",
    "sm2_encrypt",
    "sm2_decrypt",
    "sm2_sign",
    "sm2_verify",
    "sm3_hash",
    "sm3_hmac",
    "sm4_encrypt_cbc",
    "sm4_decrypt_cbc",
    "sm4_encrypt_gcm",
    "sm4_decrypt_gcm",
]
