"""
A2A Secure Transport — mTLS + 身份验证

为 A2A 协议提供安全传输层，支持：
- 双向 TLS (mTLS) 证书验证
- 请求签名与验证
- 对等身份校验
"""

from __future__ import annotations

import datetime
import ssl
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def create_self_signed_cert(agent_id: str) -> tuple[str, str]:
    """为测试创建自签名证书。

    Returns:
        Tuple[证书路径, 私钥路径]
    """
    # 生成 RSA 密钥对
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # 构建证书主题
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, agent_id),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MAREF"),
        ]
    )

    # 构建证书
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # 写入临时文件
    cert_dir = tempfile.mkdtemp(prefix="maref_certs_")
    cert_path = Path(cert_dir) / f"{agent_id}.crt"
    key_path = Path(cert_dir) / f"{agent_id}.key"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return str(cert_path), str(key_path)


@dataclass
class CertificateManager:
    """证书管理器 — 加载和验证证书。"""

    cert_path: str | None = None
    key_path: str | None = None
    ca_path: str | None = None

    def verify_peer_cert(self, peer_cert_path: str) -> bool:
        """验证对等证书是否由信任的 CA 签发。"""
        if self.ca_path is None:
            # 无 CA 配置时，仅接受相同证书（自签名场景）
            return peer_cert_path == self.cert_path

        try:
            with open(self.ca_path, "rb") as f:
                ca_cert = x509.load_pem_x509_certificate(f.read())
            with open(peer_cert_path, "rb") as f:
                peer_cert = x509.load_pem_x509_certificate(f.read())

            # 简化验证：检查颁发者是否匹配
            # 实际场景应使用 OpenSSL 的完整链验证
            return peer_cert.issuer == ca_cert.subject
        except Exception:
            return False


@dataclass
class A2ASecureTransport:
    """A2A 安全传输层。

    使用 mTLS 保护 A2A 通信，提供：
    - 客户端证书身份验证
    - 请求签名
    - 对等身份校验
    """

    base_url: str
    cert_path: str | None = None
    key_path: str | None = None
    ca_path: str | None = None
    verify_ssl: bool = True
    allowed_peers: list[str] | None = None
    agent_id: str = "urn:agent:maref:0-35-0-beta:transport"
    cert_manager: CertificateManager | None = None
    signing_key: Any | None = None
    peer_public_key: str = ""

    def __post_init__(self) -> None:
        if self.cert_path and self.key_path:
            self.cert_manager = CertificateManager(
                cert_path=self.cert_path,
                key_path=self.key_path,
                ca_path=self.ca_path,
            )

        # 强制 HTTPS（除非显式关闭验证）
        if not self.base_url.startswith("https://") and self.verify_ssl:
            if self.cert_path:
                raise ValueError(
                    "A2ASecureTransport requires HTTPS when client certificates are provided. "
                    "Use verify_ssl=False for development only."
                )

    def create_ssl_context(self) -> ssl.SSLContext | None:
        """创建 SSL 上下文（mTLS 配置）。"""
        if not self.cert_path or not self.key_path:
            return None

        context = ssl.create_default_context()
        context.load_cert_chain(self.cert_path, self.key_path)

        if self.ca_path:
            context.load_verify_locations(self.ca_path)
        else:
            # 自签名场景：禁用主机名验证（仅限测试）
            context.check_hostname = False

        if self.verify_ssl:
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context.verify_mode = ssl.CERT_NONE

        return context

    def prepare_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """准备安全请求。"""
        body = payload.encode("utf-8") if isinstance(payload, str) else str(payload).encode("utf-8")
        headers = self.get_auth_headers(body)

        return {
            "url": self.base_url,
            "method": "POST",
            "headers": headers,
            "body": body,
        }

    def get_auth_headers(self, payload: bytes) -> dict[str, str]:
        """生成认证请求头。"""
        timestamp = str(int(time.time()))
        signature = self.sign_payload(payload)

        return {
            "Content-Type": "application/json",
            "X-A2A-Agent-Id": self.agent_id,
            "X-A2A-Signature": signature,
            "X-A2A-Timestamp": timestamp,
        }

    def sign_payload(self, payload: bytes) -> str:
        """使用 Ed25519 私钥对请求体签名（v0.47 S8）。

        原先的实现把 TLS 私钥的前 32 字节当作 HMAC 密钥——那不是真正的
        签名。现在要求显式传入 :class:`ReportSigningKey`（Ed25519）。
        """
        if self.signing_key is None:
            return ""
        try:
            return self.signing_key.sign_report(payload)
        except Exception:
            return ""

    def verify_payload_signature(self, payload: bytes, signature: str) -> bool:
        """用对等方公钥验证请求签名（需配置 ``peer_public_key``）。"""
        if not signature or self.peer_public_key is None:
            return False
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            self.peer_public_key, signature, payload
        )

    def verify_peer_identity(self, peer_cert: dict[str, Any]) -> bool:
        """验证对等方身份。

        Args:
            peer_cert: 对等证书信息，如 {"subject": {"commonName": "peer-agent"}}

        Returns:
            是否允许连接
        """
        if self.allowed_peers is None:
            return True

        subject = peer_cert.get("subject", {})
        cn = subject.get("commonName", "")
        return cn in self.allowed_peers
