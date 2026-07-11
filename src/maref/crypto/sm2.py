"""SM2 椭圆曲线公钥密码算法封装.

基于 gmssl 的纯 Python 实现，提供与 cryptography 库风格一致的 API。
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING
from gmssl import func
from gmssl import sm2 as _sm2
if TYPE_CHECKING:
    pass

@dataclass(frozen=True)
class SM2KeyPair:
    """SM2 密钥对.

    Attributes:
        private_key: 32 字节 hex 字符串（64 字符），带 00 前缀时为 66 字符
        public_key: 65 字节 hex 字符串（130 字符），04 开头未压缩格式
    """
    private_key: str
    public_key: str

    @classmethod
    def generate(cls) -> SM2KeyPair:
        """生成新的 SM2 密钥对.

        使用 gmssl 的 func.random_hex 生成私钥，通过底层椭圆曲线
        点乘运算推导公钥。公钥格式为 04 || X || Y（未压缩，130 hex 字符）。
        """
        private_key = '00' + func.random_hex(64)
        public_key = _derive_public_key(private_key)
        return cls(private_key=private_key, public_key=public_key)

def _derive_public_key(private_key: str) -> str:
    """从私钥推导 SM2 公钥（基于国密推荐曲线参数）.

    使用椭圆曲线点乘 k * G，其中 G 为 SM2 曲线基点。
    返回未压缩公钥：04 || X(32字节) || Y(32字节)，共 130 个 hex 字符。
    """
    d_hex = private_key[2:] if private_key.startswith('00') else private_key
    d = int(d_hex, 16)
    p = 115792089210356248756420345214020892766250353991924191454421193933289684991999
    a = 115792089210356248756420345214020892766250353991924191454421193933289684991996
    n = 115792089210356248756420345214020892766061623724957744567843809356293439045923
    gx = 22963146547237050559479531362550074578802567295341616970375194840604139615431
    gy = 85132369209828568825618990617112496413088388631904505083283536607588877201568

    def _inv_mod(x: int, m: int) -> int:
        """模逆元（扩展欧几里得算法）."""
        return pow(x, m - 2, m)

    def _point_add(px: int, py: int, qx: int, qy: int) -> tuple[int, int]:
        """椭圆曲线点加."""
        if px == 0 and py == 0:
            return (qx, qy)
        if qx == 0 and qy == 0:
            return (px, py)
        if px == qx and py == p - qy:
            return (0, 0)
        if px == qx and py == qy:
            lam = (3 * px * px + a) * _inv_mod(2 * py, p) % p
        else:
            lam = (qy - py) * _inv_mod(qx - px, p) % p
        rx = (lam * lam - px - qx) % p
        ry = (lam * (px - rx) - py) % p
        return (rx, ry)

    def _scalar_mult(k: int, px: int, py: int) -> tuple[int, int]:
        """椭圆曲线标量乘法（double-and-add）."""
        (rx, ry) = (0, 0)
        (bx, by) = (px, py)
        while k > 0:
            if k & 1:
                (rx, ry) = _point_add(rx, ry, bx, by)
            (bx, by) = _point_add(bx, by, bx, by)
            k >>= 1
        return (rx, ry)
    (qx, qy) = _scalar_mult(d % n, gx, gy)
    return '04' + f'{qx:064x}' + f'{qy:064x}'

def _strip_sm2_prefix(public_key: str) -> str:
    """去掉 SM2 未压缩公钥的 04 前缀.

    gmssl 的 CryptSM2 使用 lstrip('04') 去掉前缀，这会错误地
    截断公钥中后续出现的 0 或 4 字符。我们手动精确去掉前缀。
    """
    if public_key.startswith('04') and len(public_key) == 130:
        return public_key[2:]
    return public_key

def sm2_encrypt(public_key: str, plaintext: bytes) -> bytes:
    """SM2 公钥加密.

    Args:
        public_key: 65 字节 hex 字符串（130 字符），04 开头
        plaintext: 待加密数据

    Returns:
        加密后的密文
    """
    crypt = _sm2.CryptSM2(public_key=_strip_sm2_prefix(public_key), private_key='')
    return crypt.encrypt(plaintext)

def sm2_decrypt(private_key: str, ciphertext: bytes) -> bytes:
    """SM2 私钥解密.

    Args:
        private_key: 32 字节 hex 字符串（64 字符），带 00 前缀时为 66 字符
        ciphertext: 密文

    Returns:
        解密后的明文
    """
    crypt = _sm2.CryptSM2(public_key='', private_key=private_key)
    return crypt.decrypt(ciphertext)

def sm2_sign(private_key: str, data: bytes, public_key: str='', *, use_sm3: bool=True) -> str:
    """SM2 签名.

    Args:
        private_key: 私钥 hex 字符串
        data: 待签名数据
        public_key: 公钥 hex 字符串（sign_with_sm3 模式下不需要）
        use_sm3: 是否使用 SM3 作为哈希算法（推荐，符合国标）

    Returns:
        hex 格式的签名值
    """
    crypt = _sm2.CryptSM2(public_key=_strip_sm2_prefix(public_key), private_key=private_key)
    if use_sm3:
        return crypt.sign_with_sm3(data)
    random_hex = func.random_hex(crypt.para_len)
    return crypt.sign(data, random_hex)

def sm2_verify(public_key: str, data: bytes, signature: str, *, use_sm3: bool=True) -> bool:
    """SM2 签名验证.

    Args:
        public_key: 公钥 hex 字符串
        data: 原始数据
        signature: hex 格式的签名值
        use_sm3: 是否使用 SM3 哈希算法

    Returns:
        验证是否通过
    """
    crypt = _sm2.CryptSM2(public_key=_strip_sm2_prefix(public_key), private_key='')
    if use_sm3:
        return crypt.verify_with_sm3(signature, data)
    return crypt.verify(signature, data)