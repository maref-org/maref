"""v0.47 S8 — replace fake signatures with real Ed25519.

Three fake-signature sites are hardened:

1. ``SecureProtocolBridge.verify_and_convert_mcp_to_a2a`` used a SHA-256
   hash of ``{agent_did}:{message_id}`` compared for equality — anyone who
   knows the DID and message id can forge it.  Replaced with real Ed25519
   verification against the peer's public key.

2. ``a2a_secure_transport.A2ASecureTransport.sign_payload`` used the first
   32 bytes of the TLS private key as an HMAC key — not a real signature.
   Replaced with standard Ed25519 signing.

3. ``mcp_security`` OAuth JWT parsing decoded the payload without verifying
   the signature.  Signature verification is added.
"""

from __future__ import annotations

import hashlib

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.protocols.protocol_bridge import (
    MCPMessage,
    SecureProtocolBridge,
    create_secure_protocol_bridge,
)
from maref.signing.signing_key import ReportSigningKey


def _make_bridge_with_peers(
    peer_public_keys: dict[str, str] | None = None,
    signing_key: ReportSigningKey | None = None,
) -> SecureProtocolBridge:
    return create_secure_protocol_bridge(
        peer_public_keys=peer_public_keys,
        signing_key=signing_key,
    )


class TestProtocolBridgeEd25519:
    def test_valid_ed25519_signature_accepted(self) -> None:
        """A genuine Ed25519 signature over the canonical payload passes."""
        peer_key = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:agent-1": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        payload = f"did:agent-1:{mcp_msg.message_id}".encode("utf-8")
        sig = peer_key.sign_report(payload)
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", sig
        )
        assert task is not None
        assert task.agent_id == "agent-2"

    def test_sha256_forgery_rejected(self) -> None:
        """The old SHA-256 'signature' is no longer accepted."""
        peer_key = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:agent-1": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        forged = hashlib.sha256(f"did:agent-1:{mcp_msg.message_id}".encode()).hexdigest()
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", forged
        )
        assert task is None

    def test_wrong_key_rejected(self) -> None:
        """A signature from a different key is rejected."""
        peer_key = ReportSigningKey.generate()
        attacker = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:agent-1": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        payload = f"did:agent-1:{mcp_msg.message_id}".encode("utf-8")
        sig = attacker.sign_report(payload)
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", sig
        )
        assert task is None

    def test_tampered_message_id_rejected(self) -> None:
        """Signing covers the message id; altering it invalidates the sig."""
        peer_key = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:agent-1": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        payload = f"did:agent-1:{mcp_msg.message_id}".encode("utf-8")
        sig = peer_key.sign_report(payload)
        # Replay the same signature against a different message id.
        tampered = MCPMessage(message_id="msg-2", method="tools/call", params={})
        task = bridge.verify_and_convert_mcp_to_a2a(
            tampered, "agent-2", "did:agent-1", sig
        )
        assert task is None

    def test_unknown_peer_public_key_rejected(self) -> None:
        """No public key registered for the agent → fail-closed."""
        peer_key = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:other": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        payload = f"did:agent-1:{mcp_msg.message_id}".encode("utf-8")
        sig = peer_key.sign_report(payload)
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", sig
        )
        assert task is None

    def test_replay_protection_still_works(self) -> None:
        """Replay protection remains after switching to Ed25519."""
        peer_key = ReportSigningKey.generate()
        bridge = _make_bridge_with_peers(
            peer_public_keys={"did:agent-1": peer_key.public_key_pem}
        )
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        payload = f"did:agent-1:{mcp_msg.message_id}".encode("utf-8")
        sig = peer_key.sign_report(payload)
        assert bridge.verify_and_convert_mcp_to_a2a(mcp_msg, "agent-2", "did:agent-1", sig) is not None
        assert bridge.verify_and_convert_mcp_to_a2a(mcp_msg, "agent-2", "did:agent-1", sig) is None


class TestA2ASecureTransportEd25519:
    def test_sign_payload_uses_ed25519(self) -> None:
        """sign_payload produces a verifiable Ed25519 signature (not an
        HMAC of the TLS key's first 32 bytes)."""
        from maref.integration.a2a_secure_transport import A2ASecureTransport

        key = ReportSigningKey.generate()
        transport = A2ASecureTransport(
            base_url="http://localhost:8080",
            verify_ssl=False,
            signing_key=key,
        )
        payload = b'{"method":"tasks/send","id":1}'
        signature = transport.sign_payload(payload)
        assert signature
        from maref.signing.signing_key import ReportSigningKey as _RSK

        assert _RSK.verify_signature(key.public_key_pem, signature, payload) is True

    def test_sign_payload_changes_with_payload(self) -> None:
        from maref.integration.a2a_secure_transport import A2ASecureTransport

        key = ReportSigningKey.generate()
        transport = A2ASecureTransport(
            base_url="http://localhost:8080",
            verify_ssl=False,
            signing_key=key,
        )
        sig1 = transport.sign_payload(b"payload-1")
        sig2 = transport.sign_payload(b"payload-2")
        assert sig1 != sig2


class TestMCPOAuthJWTVerification:
    def test_jwt_with_tampered_signature_rejected(self) -> None:
        """A JWT whose payload was modified after signing is rejected."""
        import base64
        import hashlib
        import hmac
        import json
        import time

        from maref.integration.mcp_security import OAuthMiddleware, OAuthTokenProvider

        secret = b"test-jwt-secret"
        provider = OAuthTokenProvider()
        middleware = OAuthMiddleware(token_provider=provider)
        middleware._verification_key = secret

        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "agent-1", "exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=").decode()
        signing_input = f"{header}.{payload}"
        sig = base64.urlsafe_b64encode(
            hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()

        # Modify the payload AFTER signing → signature no longer matches.
        forged_payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker", "exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=").decode()
        forged_token = f"{header}.{forged_payload}.{sig}"

        import asyncio

        with pytest.raises(PermissionError):
            asyncio.run(
                middleware.authenticate({"Authorization": f"Bearer {forged_token}"})
            )

    def test_valid_jwt_accepted(self) -> None:
        import base64
        import hashlib
        import hmac
        import json
        import time

        from maref.integration.mcp_security import OAuthMiddleware, OAuthTokenProvider

        secret = b"test-jwt-secret"
        provider = OAuthTokenProvider()
        middleware = OAuthMiddleware(token_provider=provider)
        middleware._verification_key = secret

        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "agent-1", "exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=").decode()
        signing_input = f"{header}.{payload}"
        sig = base64.urlsafe_b64encode(
            hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}.{sig}"

        import asyncio

        ctx = asyncio.run(
            middleware.authenticate({"Authorization": f"Bearer {token}"})
        )
        assert ctx.agent_id == "agent-1"

    def test_unsigned_jwt_rejected_when_key_configured(self) -> None:
        import base64
        import json
        import time

        from maref.integration.mcp_security import OAuthMiddleware, OAuthTokenProvider

        middleware = OAuthMiddleware(token_provider=OAuthTokenProvider())
        middleware._verification_key = b"test-jwt-secret"

        # A JWT with an empty/invalid signature must be rejected.
        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "agent-1", "exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}.Zm9yZ2Vk"

        import asyncio

        with pytest.raises(PermissionError):
            asyncio.run(
                middleware.authenticate({"Authorization": f"Bearer {token}"})
            )
