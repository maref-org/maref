"""ACPs AIA 身份认证协议 — 国密适配层.

实现 AIA 认证握手中的国密 SM2/SM3/SM4 算法集成：
- mTLS 握手时的国密加密套件协商
- CAI（智能体身份证书）的 SM2 签名验证 + SM3 哈希
- CertificateVerify 的 SM2 签名验证
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING
from .sm2 import sm2_sign, sm2_verify
from .sm3 import sm3_hash
if TYPE_CHECKING:
    pass

@dataclass(frozen=True)
class AgentIdentityCertificate:
    """智能体身份证书 (CAI).

    对应 ACPs AIA 协议中的 CAI 数据结构。
    """
    agent_id: str
    public_key: str
    signature: str
    casp_id: str
    validity_period: tuple[int, int]

@dataclass(frozen=True)
class AIAHandshakeContext:
    """AIA 握手上下文.

    保存 mTLS 握手过程中的关键参数，用于 CertificateVerify 验证。
    """
    client_random: bytes
    server_random: bytes
    cipher_suite: str
    handshake_messages: bytes

def verify_cai_certificate(cai: AgentIdentityCertificate, casp_public_key: str) -> bool:
    """验证 CAI 证书合法性.

    对应 AIA 协议 §3(7) 步骤 ①-③：
    1. 将 CAI 明文与签名分开
    2. 使用 SM3 哈希明文得到 Hash1
    3. 使用 CASP 公钥验证签名得到 Hash2
    4. 比对 Hash1 == Hash2

    Args:
        cai: 智能体身份证书
        casp_public_key: CASP 机构公钥 (SM2 hex)

    Returns:
        验证是否通过
    """
    cai_plaintext = f'{cai.agent_id}:{cai.public_key}:{cai.casp_id}:{cai.validity_period[0]}:{cai.validity_period[1]}'.encode()
    sm3_hash(cai_plaintext)
    try:
        verified = sm2_verify(casp_public_key, cai_plaintext, cai.signature, use_sm3=True)
        return verified
    except Exception:
        return False

def verify_certificate_verify(public_key: str, handshake_messages: bytes, signature: str) -> bool:
    """验证 CertificateVerify 消息.

    对应 AIA 协议 §3(7) 步骤：
    - 使用 signature_algorithms 指定的签名算法（SM2）
    - 使用对方证书中的公钥验证签名
    - 签名内容 = 所有握手消息的 SM3 哈希

    Args:
        public_key: 对方 SM2 公钥
        handshake_messages: 所有握手消息串联
        signature: CertificateVerify 中的签名值

    Returns:
        验证是否通过
    """
    sm3_hash(handshake_messages)
    return sm2_verify(public_key, handshake_messages, signature, use_sm3=True)

def generate_certificate_verify(private_key: str, public_key: str, handshake_messages: bytes) -> str:
    """生成 CertificateVerify 签名.

    Args:
        private_key: 己方 SM2 私钥
        public_key: 己方 SM2 公钥（gmssl sign_with_sm3 需要）
        handshake_messages: 所有握手消息串联

    Returns:
        hex 格式的签名值
    """
    return sm2_sign(private_key, handshake_messages, public_key=public_key, use_sm3=True)

def check_agent_identity(received_aic: str, cai: AgentIdentityCertificate) -> bool:
    """比对对方 AIC 与 CAI 中的 AIC 是否一致.

    对应 AIA 协议 §3(7)：验证 CAI 明文中的 AIC 与收到的 AIC 是否匹配。

    Args:
        received_aic: 收到的智能体身份码
        cai: 证书中的智能体身份码

    Returns:
        是否一致
    """
    return received_aic == cai.agent_id