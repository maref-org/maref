"""SM3 哈希算法封装.

基于 gmssl 的纯 Python 实现，提供与 hashlib 风格一致的 API。
"""
from typing import TYPE_CHECKING
from gmssl import sm3 as _sm3
if TYPE_CHECKING:
    pass

def sm3_hash(data: bytes) -> str:
    """SM3 哈希计算.

    Args:
        data: 待哈希数据

    Returns:
        64 字符 hex 字符串（256 位）
    """
    return _sm3.sm3_hash(list(data))

def sm3_hmac(key: bytes, data: bytes) -> str:
    """SM3-HMAC 消息认证码.

    Args:
        key: HMAC 密钥
        data: 待认证数据

    Returns:
        64 字符 hex 字符串
    """
    block_size = 64
    if len(key) > block_size:
        key = bytes.fromhex(sm3_hash(key))
    if len(key) < block_size:
        key = key + b'\x00' * (block_size - len(key))
    ipad = bytes([b ^ 54 for b in key])
    opad = bytes([b ^ 92 for b in key])
    inner = sm3_hash(ipad + data)
    outer = sm3_hash(opad + bytes.fromhex(inner))
    return outer