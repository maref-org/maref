from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from maref.security.agent_identity import (
    ATPAdapter,
    ATPIdentity,
    ATPVerificationResult,
    ATPChallenge,
    ATPConfig,
)


class TestATPConfig:
    def test_default_config(self):
        config = ATPConfig()
        assert config.endpoint == "https://api.lyrie.ai/atp/v1"
        assert config.timeout_seconds == 30
        assert config.retry_attempts == 3

    def test_custom_config(self):
        config = ATPConfig(
            endpoint="https://custom.example.com",
            timeout_seconds=60,
            api_key="test-key"
        )
        assert config.endpoint == "https://custom.example.com"
        assert config.timeout_seconds == 60
        assert config.api_key == "test-key"


class TestATPIdentity:
    def test_identity_creation(self):
        identity = ATPIdentity(
            agent_id="agent-001",
            public_key="-----BEGIN PUBLIC KEY-----\nMIIB...",
            registered_at=datetime.now(timezone.utc),
        )
        assert identity.agent_id == "agent-001"
        assert identity.is_verified is False
        assert identity.trust_score == 0.0

    def test_identity_verified(self):
        identity = ATPIdentity(
            agent_id="agent-001",
            public_key="-----BEGIN PUBLIC KEY-----\nMIIB...",
            registered_at=datetime.now(timezone.utc),
            is_verified=True,
            trust_score=0.85,
        )
        assert identity.is_verified is True
        assert identity.trust_score == 0.85


class TestATPChallenge:
    def test_challenge_creation(self):
        challenge = ATPChallenge.create("agent-001")
        assert challenge.agent_id == "agent-001"
        assert challenge.nonce is not None
        assert challenge.timestamp is not None
        assert challenge.expires_at > challenge.timestamp

    def test_challenge_expiration(self):
        from datetime import timedelta
        challenge = ATPChallenge.create("agent-001", ttl_seconds=1)
        assert not challenge.is_expired()
        # Note: In real tests, we'd mock time


class TestATPAdapter:
    def test_adapter_initialization(self):
        config = ATPConfig()
        adapter = ATPAdapter(config)
        assert adapter.config == config

    @patch('maref.security.agent_identity.ATPAdapter._make_request')
    def test_register_identity(self, mock_request):
        mock_request.return_value = {
            "status": "registered",
            "agent_id": "agent-001",
            "certificate": "cert-12345",
        }
        
        adapter = ATPAdapter(ATPConfig())
        result = adapter.register_identity("agent-001", "-----BEGIN PUBLIC KEY-----\nMIIB...")
        
        assert result is True
        mock_request.assert_called_once()

    @patch('maref.security.agent_identity.ATPAdapter._make_request')
    def test_verify_identity_success(self, mock_request):
        mock_request.return_value = {
            "status": "verified",
            "agent_id": "agent-001",
            "trust_score": 0.92,
            "capabilities": ["read", "write"],
        }
        
        adapter = ATPAdapter(ATPConfig())
        result = adapter.verify_identity("agent-001")
        
        assert result.is_valid is True
        assert result.agent_id == "agent-001"
        assert result.trust_score == 0.92

    @patch('maref.security.agent_identity.ATPAdapter._make_request')
    def test_verify_identity_failure(self, mock_request):
        mock_request.return_value = {
            "status": "unverified",
            "agent_id": "agent-001",
            "reason": "certificate_expired",
        }
        
        adapter = ATPAdapter(ATPConfig())
        result = adapter.verify_identity("agent-001")
        
        assert result.is_valid is False
        assert result.reason == "certificate_expired"

    @patch('maref.security.agent_identity.ATPAdapter._make_request')
    def test_create_challenge(self, mock_request):
        mock_request.return_value = {
            "nonce": "abc123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.now(timezone.utc).isoformat(),
        }
        
        adapter = ATPAdapter(ATPConfig())
        challenge = adapter.create_challenge("agent-001")
        
        assert challenge.agent_id == "agent-001"
        assert challenge.nonce == "abc123"

    @patch('maref.security.agent_identity.ATPAdapter._make_request')
    def test_verify_challenge_response(self, mock_request):
        mock_request.return_value = {
            "status": "verified",
            "agent_id": "agent-001",
            "trust_score": 0.95,
        }
        
        adapter = ATPAdapter(ATPConfig())
        challenge = ATPChallenge.create("agent-001")
        response = {"signature": "sig-123", "nonce": challenge.nonce}
        
        result = adapter.verify_challenge_response("agent-001", challenge, response)
        
        assert result.is_valid is True
        assert result.trust_score == 0.95

    def test_local_verification_fallback(self):
        """Test that adapter works in local/offline mode"""
        config = ATPConfig(endpoint="", enable_local_fallback=True)
        adapter = ATPAdapter(config)
        
        # Should not raise even without network
        result = adapter.verify_identity("agent-001")
        assert result.is_valid is False  # Local mode returns unverified
        assert result.reason == "local_mode"
        
        # Should not raise even without network
        result = adapter.verify_identity("agent-001")
        assert result.is_valid is False  # Local mode returns unverified
        assert result.reason == "local_mode"


class TestATPIntegration:
    def test_full_identity_lifecycle(self):
        """Test register -> challenge -> verify flow"""
        config = ATPConfig(endpoint="https://test.example.com", enable_local_fallback=True)
        adapter = ATPAdapter(config)
        
        # Step 1: Register
        with patch.object(adapter, '_make_request') as mock_req:
            mock_req.return_value = {"status": "registered", "agent_id": "agent-001"}
            assert adapter.register_identity("agent-001", "pubkey-123") is True
        
        # Step 2: Create challenge
        now = datetime.now(timezone.utc)
        with patch.object(adapter, '_make_request') as mock_req:
            mock_req.return_value = {
                "nonce": "challenge-123",
                "timestamp": now.isoformat(),
                "expires_at": (now + timedelta(seconds=300)).isoformat(),
            }
            challenge = adapter.create_challenge("agent-001")
            assert challenge.nonce == "challenge-123"
        
        # Step 3: Verify
        with patch.object(adapter, '_make_request') as mock_req:
            mock_req.return_value = {
                "status": "verified",
                "agent_id": "agent-001",
                "trust_score": 0.88,
            }
            result = adapter.verify_identity("agent-001")
            assert result.is_valid is True
            assert result.trust_score == 0.88


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
