"""Tests for VerificationBridge — PERCV verification protocols to MAREF bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.percv.verification_bridge import VerificationBridge, VerificationResult


class TestVerificationResult:
    def test_defaults(self) -> None:
        vr = VerificationResult(protocol="A", passed=True, confidence=0.8)
        assert vr.protocol == "A"
        assert vr.passed
        assert vr.confidence == 0.8


class TestVerificationBridge:
    def test_init(self) -> None:
        bridge = VerificationBridge()
        assert bridge._history == []

    def test_protocol_a_no_gateway(self) -> None:
        bridge = VerificationBridge()
        results = bridge.run_protocol_a([{"claim": "test claim"}])
        assert len(results) == 1
        assert not results[0].passed
        assert "GatewayAdapter" in results[0].error

    def test_protocol_a_with_gateway(self) -> None:
        gateway = MagicMock()
        resp_a = MagicMock()
        resp_a.content = "Extracted: value X"
        resp_b = MagicMock()
        resp_b.content = "Extracted: value X"
        gateway.chat_with_verification.return_value = (resp_a, resp_b)

        bridge = VerificationBridge(gateway_adapter=gateway)
        results = bridge.run_protocol_a([{"claim": "Revenue grew 20%"}])

        assert len(results) == 1
        assert results[0].protocol == "A"

    def test_protocol_a_with_trust_graph(self) -> None:
        gateway = MagicMock()
        resp_a = MagicMock()
        resp_a.content = "Verified: 80%"
        resp_b = MagicMock()
        resp_b.content = "Verified: 80%"
        gateway.chat_with_verification.return_value = (resp_a, resp_b)

        tg = MagicMock()
        bridge = VerificationBridge(gateway_adapter=gateway, trust_graph=tg)
        results = bridge.run_protocol_a(
            [
                {"kdp_id": "K-001", "claim": "80% market share"},
            ]
        )

        assert len(results) == 1
        assert results[0].confidence > 0.5

    def test_protocol_b_fallback(self) -> None:
        gateway = MagicMock()
        router = MagicMock()
        router.adversarial_call.return_value = {
            "transcript": [{"round": 1, "attack": "x", "defense": "y"}],
            "verdict": '{"confidence": 75, "recommendation": "accept"}',
        }
        gateway._ensure_router.return_value = router

        bridge = VerificationBridge(gateway_adapter=gateway)
        result = bridge.run_protocol_b(
            hypothesis="AI will replace X",
            context="Industry context",
        )

        assert result.protocol == "B"
        assert result.confidence == 0.75

    def test_protocol_b_with_maref_redblue(self) -> None:
        rb = MagicMock()
        rb.run_adversarial.return_value = {
            "verdict": {"confidence": 85},
        }

        bridge = VerificationBridge(redblue_engine=rb)
        result = bridge.run_protocol_b(
            hypothesis="test",
            context="context",
        )

        assert result.protocol == "B"
        assert result.passed

    def test_protocol_c_valid_forecast(self) -> None:
        bridge = VerificationBridge()
        result = bridge.run_protocol_c(
            {
                "linked_kdps": ["K-001", "K-002"],
                "assumptions": [{"text": "assumption 1"}],
                "core_forecast": "If A then B",
            }
        )
        assert result.passed
        assert result.confidence == 0.8

    def test_protocol_c_invalid_forecast(self) -> None:
        bridge = VerificationBridge()
        result = bridge.run_protocol_c(
            {
                "linked_kdps": [],
                "assumptions": [],
                "core_forecast": "",
            }
        )
        assert not result.passed
        assert "no_linked_kdps" in result.details["chain_issues"]

    def test_protocol_d_no_gateway(self) -> None:
        bridge = VerificationBridge()
        results = bridge.run_protocol_d(
            [
                {"metric_type": "exact_number", "claim": "100M users"},
            ]
        )
        assert len(results) == 1
        assert "GatewayAdapter" in results[0].error

    def test_protocol_d_with_gateway(self) -> None:
        gateway = MagicMock()
        router = MagicMock()
        router.triangulate_facts.return_value = [
            {
                "metric_type": "exact_number",
                "verification_results": {
                    "sf-deepseek": "VERIFIED: 100M",
                    "sf-kimi": "VERIFIED: 100M",
                    "sf-qwen": "VERIFIED: 100M",
                },
            }
        ]
        gateway._ensure_router.return_value = router

        bridge = VerificationBridge(gateway_adapter=gateway)
        results = bridge.run_protocol_d(
            [
                {"metric_type": "exact_number", "claim": "100M users"},
            ]
        )

        assert len(results) == 1
        assert results[0].passed
        assert results[0].confidence >= 0.5

    def test_get_history(self) -> None:
        bridge = VerificationBridge()
        assert bridge.get_history() == []
        bridge._history.append(
            VerificationResult(protocol="A", passed=True, confidence=0.9),
        )
        assert len(bridge.get_history()) == 1

    def test_get_summary_empty(self) -> None:
        bridge = VerificationBridge()
        summary = bridge.get_summary()
        assert summary["status"] == "no_activity"

    def test_get_summary_with_results(self) -> None:
        bridge = VerificationBridge()
        bridge._history = [
            VerificationResult(protocol="A", passed=True, confidence=0.9),
            VerificationResult(protocol="B", passed=True, confidence=0.7),
            VerificationResult(protocol="C", passed=False, confidence=0.3),
        ]
        summary = bridge.get_summary()
        assert summary["total_verifications"] == 3
        assert summary["passed"] == 2
        assert summary["by_protocol"]["A"]["total"] == 1
        assert summary["by_protocol"]["A"]["avg_confidence"] == 0.9

    def test_compute_consensus_identical(self) -> None:
        bridge = VerificationBridge()
        c = bridge._compute_consensus("The answer is 42", "The answer is 42")
        assert c["agreement"]

    def test_compute_consensus_different(self) -> None:
        bridge = VerificationBridge()
        c = bridge._compute_consensus("Alpha", "Beta Gamma Delta Epsilon")
        assert not c["agreement"]

    def test_compute_consensus_empty(self) -> None:
        bridge = VerificationBridge()
        c = bridge._compute_consensus("", "")
        assert not c["agreement"]
