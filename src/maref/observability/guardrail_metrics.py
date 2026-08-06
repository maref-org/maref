from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

_HAS_PROMETHEUS = False
try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

    _HAS_PROMETHEUS = True
except ImportError:
    pass


@dataclass
class GuardrailCheckRecord:
    verdict: str
    gate: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class RiskScoreRecord:
    agent_id: str
    score: float
    timestamp: float = field(default_factory=time.time)


def _make_histogram_buckets() -> list[float]:
    return [0.001, 0.005, 0.01, 0.05, 0.1]


class GuardrailMetricsCollector:
    """Collects and exposes guardrail check metrics.

    Tracks guardrail check verdicts (ALLOW/DENY/AUDIT), risk scores per agent,
    active denial counts, and open circuit breaker counts. Supports Prometheus
    exposition format and in-memory fallback when prometheus_client is not installed.
    """

    def __init__(self) -> None:
        """Initialize the metrics collector.

        Sets up thread-safe locks, in-memory storage, and Prometheus metrics
        (Counter, Histogram, Gauge) if prometheus_client is available.
        """
        self._lock = threading.Lock()
        self._checks: list[GuardrailCheckRecord] = []
        self._risk_scores: dict[str, RiskScoreRecord] = {}
        self._active_denials: int = 0
        self._open_circuit_breakers: int = 0

        if _HAS_PROMETHEUS:
            self._counter = Counter(
                "guardrail_checks_total",
                "Total guardrail checks",
                ["verdict", "gate"],
                registry=REGISTRY,
            )
            self._histogram = Histogram(
                "guardrail_check_duration_seconds",
                "Guardrail check duration",
                ["gate"],
                buckets=_make_histogram_buckets(),
                registry=REGISTRY,
            )
            self._risk_gauge = Gauge(
                "guardrail_risk_score",
                "Current risk score per agent",
                ["agent_id"],
                registry=REGISTRY,
            )
            self._denials_gauge = Gauge(
                "guardrail_active_denials",
                "Current number of blocked requests",
                registry=REGISTRY,
            )
            self._cb_gauge = Gauge(
                "guardrail_circuit_breakers_open",
                "Number of open circuit breakers",
                registry=REGISTRY,
            )

    def record_check(self, verdict: str, gate: str, duration_ms: float) -> None:
        """Record a guardrail check result.

        Args:
            verdict: Check result — 'ALLOW', 'DENY', or 'AUDIT'. Invalid values
                default to 'AUDIT'.
            gate: The gate that performed the check — 'security', 'policy',
                'circuit_breaker', or 'hitl'. Invalid values default to 'policy'.
            duration_ms: Duration of the check in milliseconds.
        """
        valid_verdicts = {"ALLOW", "DENY", "AUDIT"}
        if verdict not in valid_verdicts:
            verdict = "AUDIT"

        valid_gates = {"security", "policy", "circuit_breaker", "hitl"}
        if gate not in valid_gates:
            gate = "policy"

        record = GuardrailCheckRecord(verdict=verdict, gate=gate, duration_ms=duration_ms)

        with self._lock:
            self._checks.append(record)
            if verdict == "DENY":
                self._active_denials += 1

        if _HAS_PROMETHEUS:
            self._counter.labels(verdict=verdict, gate=gate).inc()
            self._histogram.labels(gate=gate).observe(duration_ms / 1000.0)
            self._denials_gauge.set(self._active_denials)
            self._cb_gauge.set(self._open_circuit_breakers)

    def record_risk_score(self, agent_id: str, score: float) -> None:
        """Record a risk score for an agent.

        Args:
            agent_id: Identifier of the agent.
            score: Risk score value (clamped to 0.0–100.0).
        """
        clamped = max(0.0, min(100.0, score))
        record = RiskScoreRecord(agent_id=agent_id, score=clamped)

        with self._lock:
            self._risk_scores[agent_id] = record

        if _HAS_PROMETHEUS:
            self._risk_gauge.labels(agent_id=agent_id).set(clamped)

    def set_active_denials(self, count: int) -> None:
        """Set the count of currently blocked requests.

        Args:
            count: Number of active denials (clamped to >= 0).
        """
        with self._lock:
            self._active_denials = max(0, count)
        if _HAS_PROMETHEUS:
            self._denials_gauge.set(self._active_denials)

    def set_open_circuit_breakers(self, count: int) -> None:
        """Set the count of open circuit breakers.

        Args:
            count: Number of open circuit breakers (clamped to >= 0).
        """
        with self._lock:
            self._open_circuit_breakers = max(0, count)
        if _HAS_PROMETHEUS:
            self._cb_gauge.set(self._open_circuit_breakers)

    def get_metrics(self) -> str:
        """Get metrics in Prometheus exposition format.

        Uses prometheus_client.generate_latest() if available, otherwise
        generates a plain-text fallback with the same metric names.

        Returns:
            Prometheus-format metrics string.
        """
        if _HAS_PROMETHEUS:
            return generate_latest(registry=REGISTRY).decode("utf-8")

        with self._lock:
            allow = sum(1 for c in self._checks if c.verdict == "ALLOW")
            deny = sum(1 for c in self._checks if c.verdict == "DENY")
            audit = sum(1 for c in self._checks if c.verdict == "AUDIT")

        lines = [
            "# HELP guardrail_checks_total Total guardrail checks",
            "# TYPE guardrail_checks_total counter",
            f'guardrail_checks_total{{verdict="ALLOW",gate="all"}} {allow}',
            f'guardrail_checks_total{{verdict="DENY",gate="all"}} {deny}',
            f'guardrail_checks_total{{verdict="AUDIT",gate="all"}} {audit}',
            "",
            "# HELP guardrail_active_denials Current number of blocked requests",
            "# TYPE guardrail_active_denials gauge",
            f"guardrail_active_denials {self._active_denials}",
            "",
            "# HELP guardrail_circuit_breakers_open Number of open circuit breakers",
            "# TYPE guardrail_circuit_breakers_open gauge",
            f"guardrail_circuit_breakers_open {self._open_circuit_breakers}",
            "",
            "# HELP guardrail_risk_score Current risk score per agent",
            "# TYPE guardrail_risk_score gauge",
        ]
        with self._lock:
            for agent_id, record in self._risk_scores.items():
                lines.append(f'guardrail_risk_score{{agent_id="{agent_id}"}} {record.score}')
        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics for all recorded checks.

        Returns:
            Dictionary with total_checks, allow_rate, deny_rate, audit_rate,
            risk_scores, open_circuit_breakers, and active_denials.
        """
        with self._lock:
            total = len(self._checks)
            risk_scores = [
                {"agent_id": agent_id, "score": record.score}
                for agent_id, record in self._risk_scores.items()
            ]

            if total == 0:
                return {
                    "total_checks": 0,
                    "allow_rate": 0.0,
                    "deny_rate": 0.0,
                    "audit_rate": 0.0,
                    "risk_scores": risk_scores,
                    "open_circuit_breakers": self._open_circuit_breakers,
                    "active_denials": self._active_denials,
                }

            allow = sum(1 for c in self._checks if c.verdict == "ALLOW")
            deny = sum(1 for c in self._checks if c.verdict == "DENY")
            audit = sum(1 for c in self._checks if c.verdict == "AUDIT")

            return {
                "total_checks": total,
                "allow_rate": round(allow / total * 100, 1),
                "deny_rate": round(deny / total * 100, 1),
                "audit_rate": round(audit / total * 100, 1),
                "risk_scores": risk_scores,
                "open_circuit_breakers": self._open_circuit_breakers,
                "active_denials": self._active_denials,
            }

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get the most recent guardrail check events.

        Args:
            limit: Maximum number of events to return (default 50).

        Returns:
            List of event dicts with verdict, gate, duration, and timestamp.
        """
        with self._lock:
            recent = self._checks[-limit:]
            return [
                {
                    "verdict": c.verdict,
                    "gate": c.gate,
                    "duration": c.duration_ms,
                    "timestamp": c.timestamp,
                }
                for c in recent
            ]

    def reset_metrics(self) -> None:
        """Clear all in-memory metrics and reset counters to zero."""
        with self._lock:
            self._checks.clear()
            self._risk_scores.clear()
            self._active_denials = 0
            self._open_circuit_breakers = 0


_guardrail_metrics: GuardrailMetricsCollector | None = None


def get_guardrail_metrics() -> GuardrailMetricsCollector:
    """Get or create the global guardrail metrics singleton.

    Returns:
        The shared GuardrailMetricsCollector instance.
    """
    global _guardrail_metrics
    if _guardrail_metrics is None:
        _guardrail_metrics = GuardrailMetricsCollector()
    return _guardrail_metrics
