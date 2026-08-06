from __future__ import annotations

from pathlib import Path

import pytest

from maref.integration.a2a_secure_transport import (
    A2ASecureTransport,
    CertificateManager,
    create_self_signed_cert,
)


class TestCertificateManager:
    """P6.1: 证书管理测试"""

    def test_create_self_signed_cert(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        assert Path(cert_path).exists()
        assert Path(key_path).exists()
        # 验证是有效的 PEM 文件
        with open(cert_path) as f:
            content = f.read()
            assert "BEGIN CERTIFICATE" in content
            assert "END CERTIFICATE" in content
        with open(key_path) as f:
            content = f.read()
            assert "BEGIN" in content and "PRIVATE KEY" in content
            assert "END" in content and "PRIVATE KEY" in content

    def test_certificate_manager_load(self):
        cert_path, key_path = create_self_signed_cert("agent-1")
        cm = CertificateManager(
            cert_path=cert_path,
            key_path=key_path,
            ca_path=None,
        )
        assert cm.cert_path == cert_path
        assert cm.key_path == key_path

    def test_certificate_manager_verify_self_signed(self):
        cert_path, key_path = create_self_signed_cert("agent-1")
        cm = CertificateManager(
            cert_path=cert_path,
            key_path=key_path,
            ca_path=cert_path,  # 自签名证书作为 CA
        )
        assert cm.verify_peer_cert(cert_path) is True

    def test_certificate_manager_verify_invalid_cert(self):
        cert_path, key_path = create_self_signed_cert("agent-1")
        cert_path2, _ = create_self_signed_cert("agent-2")
        cm = CertificateManager(
            cert_path=cert_path,
            key_path=key_path,
            ca_path=cert_path,  # 只信任 agent-1
        )
        # agent-2 的证书不能被 agent-1 的 CA 验证
        assert cm.verify_peer_cert(cert_path2) is False


class TestA2ASecureTransport:
    """P6.2: A2A安全传输测试"""

    def test_secure_transport_init(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        transport = A2ASecureTransport(
            base_url="https://localhost:8443",
            cert_path=cert_path,
            key_path=key_path,
        )
        assert transport.base_url == "https://localhost:8443"
        assert transport.cert_manager is not None

    def test_secure_transport_requires_https(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        with pytest.raises(ValueError, match="HTTPS"):
            A2ASecureTransport(
                base_url="http://localhost:8080",  # 非 HTTPS
                cert_path=cert_path,
                key_path=key_path,
            )

    def test_secure_transport_allows_http_without_certs(self):
        # 没有证书时允许 HTTP（开发模式）
        transport = A2ASecureTransport(
            base_url="http://localhost:8080",
            cert_path=None,
            key_path=None,
            verify_ssl=False,
        )
        assert transport.base_url == "http://localhost:8080"

    def test_send_task_request(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        transport = A2ASecureTransport(
            base_url="https://localhost:8443",
            cert_path=cert_path,
            key_path=key_path,
            verify_ssl=False,  # 测试模式不验证服务端
        )

        # 构造任务请求
        task_request = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": "task-123",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello secure agent"}],
                },
            },
            "id": 1,
        }

        # 由于是 localhost 无真实服务，验证请求被正确构造
        prepared = transport.prepare_request(task_request)
        assert prepared["url"] == "https://localhost:8443"
        assert "X-A2A-Agent-Id" in prepared["headers"]
        assert "X-A2A-Signature" in prepared["headers"]

    def test_verify_peer_identity(self):
        cert_path, key_path = create_self_signed_cert("peer-agent")
        transport = A2ASecureTransport(
            base_url="https://localhost:8443",
            cert_path=cert_path,
            key_path=key_path,
            verify_ssl=True,
        )

        # 模拟对等证书验证
        peer_cert = {"subject": {"commonName": "peer-agent"}}
        assert transport.verify_peer_identity(peer_cert) is True

    def test_verify_peer_identity_mismatch(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        transport = A2ASecureTransport(
            base_url="https://localhost:8443",
            cert_path=cert_path,
            key_path=key_path,
            verify_ssl=True,
            allowed_peers=["expected-agent"],
        )

        peer_cert = {"subject": {"commonName": "unexpected-agent"}}
        assert transport.verify_peer_identity(peer_cert) is False

    def test_mtls_context_creation(self):
        cert_path, key_path = create_self_signed_cert("test-agent")
        ca_path, _ = create_self_signed_cert("ca")
        transport = A2ASecureTransport(
            base_url="https://localhost:8443",
            cert_path=cert_path,
            key_path=key_path,
            ca_path=ca_path,
            verify_ssl=True,
        )

        ssl_context = transport.create_ssl_context()
        assert ssl_context is not None
        # 验证 mTLS 配置: 需要客户端证书
        assert ssl_context.verify_mode.name == "CERT_REQUIRED"

    def test_sign_request_payload(self):
        from maref.signing.signing_key import ReportSigningKey

        signing_key = ReportSigningKey.generate()
        transport = A2ASecureTransport(
            base_url="http://localhost:8080",
            cert_path=None,
            key_path=None,
            verify_ssl=False,
            signing_key=signing_key,
        )

        payload = b'{"method":"tasks/send","id":1}'
        signature = transport.sign_payload(payload)
        assert signature is not None
        assert len(signature) > 0
        # Ed25519 signature verifies against the public key (v0.47 S8).
        from maref.signing.signing_key import ReportSigningKey as _RSK

        assert _RSK.verify_signature(signing_key.public_key_pem, signature, payload) is True

    def test_request_headers_include_auth(self):
        from maref.signing.signing_key import ReportSigningKey

        signing_key = ReportSigningKey.generate()
        transport = A2ASecureTransport(
            base_url="http://localhost:8080",
            cert_path=None,
            key_path=None,
            verify_ssl=False,
            signing_key=signing_key,
        )

        headers = transport.get_auth_headers(b"test payload")
        assert "X-A2A-Agent-Id" in headers
        assert "X-A2A-Signature" in headers
        assert "X-A2A-Timestamp" in headers
