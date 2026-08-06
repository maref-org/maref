"""MAREF 密码学模块.

提供国密 SM2/SM3/SM4 算法和 Ed25519 签名算法的统一封装，兼容 ACPs AIA 认证协议要求。
依赖: gmssl>=3.2.2, cryptography>=42.0
"""

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.crypto.sm2 import SM2KeyPair, sm2_decrypt, sm2_encrypt, sm2_sign, sm2_verify
from maref.crypto.sm3 import sm3_hash, sm3_hmac
from maref.crypto.sm4 import (
    SM4GCMResult,
    sm4_decrypt_cbc,
    sm4_decrypt_gcm,
    sm4_encrypt_cbc,
    sm4_encrypt_gcm,
)

__all__ = ['SM2KeyPair', 'SM4GCMResult', 'Ed25519KeyPair', 'sm2_encrypt', 'sm2_decrypt', 'sm2_sign', 'sm2_verify', 'sm3_hash', 'sm3_hmac', 'sm4_encrypt_cbc', 'sm4_decrypt_cbc', 'sm4_encrypt_gcm', 'sm4_decrypt_gcm']
