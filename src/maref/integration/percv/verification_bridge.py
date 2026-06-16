from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a verification protocol execution."""

    protocol: str  # A | B | C | D
    passed: bool
    confidence: float  # 0.0-1.0
    primary_result: str = ""
    secondary_result: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class VerificationBridge:
    """Bridges PERCV's 4 verification protocols to MAREF's security & trust layer.

    Integrates PERCV's fact-checking capabilities with MAREF's existing
    red-blue adversarial engine and trust graph:

    - Protocol A (Dual-blind KDP): → MAREF trust graph node confidence
    - Protocol B (Red-blue adversarial): → MAREF redblue engine extension
    - Protocol C (Causal chain triangulation): → MAREF governance audit trail
    - Protocol D (Fact number triangulation): → MAREF compliance validation

    Usage:
        bridge = VerificationBridge(gateway_adapter=adapter)
        result = bridge.run_protocol_a(kdp_cards)
    """

    def __init__(
        self,
        gateway_adapter: Any | None = None,
        trust_graph: Any | None = None,
        redblue_engine: Any | None = None,
    ):
        self._gateway = gateway_adapter
        self._trust_graph = trust_graph
        self._redblue = redblue_engine
        self._history: list[VerificationResult] = []

    def run_protocol_a(self, kdp_cards: list[dict[str, Any]]) -> list[VerificationResult]:
        """Dual-blind KDP extraction verification (Protocol A).

        Two independent models extract key data points from signals,
        then their results are compared for consensus.
        """
        if self._gateway is None:
            return [
                VerificationResult(
                    protocol="A",
                    passed=False,
                    confidence=0.0,
                    error="GatewayAdapter required",
                )
            ]

        results: list[VerificationResult] = []
        for kdp in kdp_cards:
            claim = kdp.get("claim", "")
            if not claim:
                continue

            messages = [
                {
                    "role": "system",
                    "content": "Extract and verify the key data point from this claim.",
                },
                {"role": "user", "content": claim},
            ]

            try:
                resp_a, resp_b = self._gateway.chat_with_verification(
                    messages,
                    protocol="A",
                )

                consensus = self._compute_consensus(resp_a.content, resp_b.content)
                result = VerificationResult(
                    protocol="A",
                    passed=consensus.get("agreement", False),
                    confidence=consensus.get("confidence", 0.5),
                    primary_result=resp_a.content[:500],
                    secondary_result=resp_b.content[:500],
                    details={"kdp_id": kdp.get("kdp_id", ""), "consensus": consensus},
                )

                if self._trust_graph and consensus.get("confidence", 0) > 0.7:
                    self._update_trust_graph(kdp, consensus)

            except Exception as exc:
                result = VerificationResult(
                    protocol="A",
                    passed=False,
                    confidence=0.0,
                    error=str(exc),
                )

            results.append(result)
            self._history.append(result)

        return results

    def run_protocol_b(
        self,
        hypothesis: str,
        context: str,
        rounds: int = 2,
    ) -> VerificationResult:
        """Red-blue adversarial hypothesis testing (Protocol B).

        Uses MAREF's redblue engine if available, otherwise falls back
        to PERCV's adversarial_call via the gateway.
        """
        if self._redblue and hasattr(self._redblue, "run_adversarial"):
            try:
                result = self._redblue.run_adversarial(
                    hypothesis=hypothesis,
                    rounds=rounds,
                )
                return VerificationResult(
                    protocol="B",
                    passed=result.get("verdict", {}).get("confidence", 50) > 60,
                    confidence=result.get("verdict", {}).get("confidence", 50) / 100.0,
                    details=result,
                )
            except Exception as exc:
                logger.warning("MAREF redblue engine failed, falling back: %s", exc)

        if self._gateway is None:
            return VerificationResult(
                protocol="B",
                passed=False,
                confidence=0.0,
                error="No verification backend available",
            )

        try:
            result = self._gateway._ensure_router().adversarial_call(
                defender="sf-deepseek",
                prosecutor="sf-kimi",
                judge="sf-qwen",
                hypothesis=hypothesis,
                context=context,
                rounds=rounds,
            )

            verdict = result.get("verdict", "{}")
            try:
                verdict_data = json.loads(verdict) if isinstance(verdict, str) else verdict
                confidence = float(verdict_data.get("confidence", 50)) / 100.0
            except (json.JSONDecodeError, ValueError, TypeError):
                confidence = 0.5

            transcript = result.get("transcript", [])
            passed = confidence > 0.6

            vr = VerificationResult(
                protocol="B",
                passed=passed,
                confidence=confidence,
                details={"transcript": transcript, "verdict": verdict},
            )
            self._history.append(vr)
            return vr

        except Exception as exc:
            return VerificationResult(
                protocol="B",
                passed=False,
                confidence=0.0,
                error=str(exc),
            )

    def run_protocol_c(self, forecast: dict[str, Any]) -> VerificationResult:
        """Causal chain triangulation (Protocol C).

        Audits the logical chain from signal → KDP → forecast for
        causal consistency.
        """
        if not forecast:
            return VerificationResult(
                protocol="C",
                passed=False,
                confidence=0.0,
                error="Empty forecast data",
            )

        linked_kdps = forecast.get("linked_kdps", [])
        assumptions = forecast.get("assumptions", [])
        core_forecast = forecast.get("core_forecast", "")

        chain_issues: list[str] = []
        if not linked_kdps:
            chain_issues.append("no_linked_kdps")
        if not assumptions:
            chain_issues.append("no_explicit_assumptions")
        if not core_forecast:
            chain_issues.append("no_core_forecast_statement")

        confidence = 0.0
        if linked_kdps and assumptions and core_forecast:
            confidence = 0.8
        elif linked_kdps and core_forecast:
            confidence = 0.5
        elif core_forecast:
            confidence = 0.3

        result = VerificationResult(
            protocol="C",
            passed=len(chain_issues) == 0,
            confidence=confidence,
            details={
                "linked_kdps_count": len(linked_kdps),
                "assumptions_count": len(assumptions),
                "chain_issues": chain_issues,
            },
        )
        self._history.append(result)
        return result

    def run_protocol_d(self, kdps: list[dict[str, Any]]) -> list[VerificationResult]:
        """Fact number triangulation (Protocol D).

        Cross-verifies numerical claims across three independent models.
        """
        if self._gateway is None:
            return [
                VerificationResult(
                    protocol="D",
                    passed=False,
                    confidence=0.0,
                    error="GatewayAdapter required for Protocol D",
                )
            ]

        results: list[VerificationResult] = []
        router = self._gateway._ensure_router()

        for kdp in kdps:
            if kdp.get("metric_type") != "exact_number":
                continue

            try:
                triangulated = router.triangulate_facts([kdp])
                verified_kdp = triangulated[0] if triangulated else kdp
                verifications = verified_kdp.get("verification_results", {})

                agreements = sum(
                    1 for v in verifications.values() if v and v.startswith("VERIFIED")
                )
                total = len(verifications)
                agreement_rate = agreements / total if total > 0 else 0.0

                result = VerificationResult(
                    protocol="D",
                    passed=agreement_rate >= 0.5,
                    confidence=agreement_rate,
                    details={
                        "kdp_id": kdp.get("kdp_id", ""),
                        "claim": kdp.get("claim", ""),
                        "value": kdp.get("value", ""),
                        "agreements": agreements,
                        "total_models": total,
                        "verifications": verifications,
                    },
                )

            except Exception as exc:
                result = VerificationResult(
                    protocol="D",
                    passed=False,
                    confidence=0.0,
                    error=str(exc),
                )

            results.append(result)
            self._history.append(result)

        return results

    def _compute_consensus(self, result_a: str, result_b: str) -> dict[str, Any]:
        """Simple heuristic consensus between two model outputs."""
        if not result_a or not result_b:
            return {"agreement": False, "confidence": 0.0}

        a_lower = result_a.lower().strip()
        b_lower = result_b.lower().strip()

        if a_lower == b_lower:
            return {"agreement": True, "confidence": 1.0}

        a_words = set(a_lower.split())
        b_words = set(b_lower.split())
        if not a_words or not b_words:
            return {"agreement": False, "confidence": 0.0}

        intersection = a_words & b_words
        jaccard = len(intersection) / len(a_words | b_words)

        return {
            "agreement": jaccard > 0.3,
            "confidence": round(jaccard, 3),
            "jaccard_similarity": round(jaccard, 3),
        }

    def _update_trust_graph(self, kdp: dict, consensus: dict) -> None:
        """Update MAREF trust graph with verification results."""
        if self._trust_graph is None:
            return
        try:
            node_id = kdp.get("kdp_id", "")
            confidence = consensus.get("confidence", 0.5)
            if hasattr(self._trust_graph, "update_node_confidence"):
                self._trust_graph.update_node_confidence(node_id, confidence)
        except Exception as exc:
            logger.debug("Trust graph update failed: %s", exc)

    def get_history(self) -> list[VerificationResult]:
        """Return all verification results from this session."""
        return list(self._history)

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate summary of all verification activity."""
        if not self._history:
            return {"status": "no_activity"}

        by_protocol: dict[str, list[VerificationResult]] = {}
        for vr in self._history:
            by_protocol.setdefault(vr.protocol, []).append(vr)

        return {
            "total_verifications": len(self._history),
            "passed": sum(1 for vr in self._history if vr.passed),
            "failed": sum(1 for vr in self._history if not vr.passed),
            "avg_confidence": round(
                sum(vr.confidence for vr in self._history) / len(self._history),
                3,
            )
            if self._history
            else 0.0,
            "by_protocol": {
                proto: {
                    "total": len(vrs),
                    "passed": sum(1 for vr in vrs if vr.passed),
                    "avg_confidence": round(
                        sum(vr.confidence for vr in vrs) / len(vrs),
                        3,
                    )
                    if vrs
                    else 0.0,
                }
                for proto, vrs in by_protocol.items()
            },
        }
