from __future__ import annotations

import asyncio
import time

import pytest

from maref.integration.mcp_governance import MCPCircuitBreakerMonitor
from maref.integration.mcp_security import (
    MCPSecurityGate,
    MCPTrustLevel,
    RateLimiter,
    ZeroTrustContext,
)
from maref.observability.guardrail_metrics import GuardrailMetricsCollector


@pytest.mark.chaos
class TestGuardrailsChaos:
    async def test_circuit_breaker_bypass_attempt(self) -> None:
        monitor = MCPCircuitBreakerMonitor(max_error_rate=0.3, min_calls_for_metrics=3)
        tool_name = "bash"

        for _ in range(5):
            monitor.record_call(tool_name, latency=0.1, success=False)

        should_trip, reason = monitor.should_trip(tool_name)
        assert should_trip, f"Circuit breaker should trip after 5 failures: {reason}"

        for _ in range(10):
            success = True
            monitor.record_call(tool_name, latency=0.05, success=success)

        should_trip_after_recovery, _ = monitor.should_trip(tool_name)
        assert should_trip_after_recovery, "Should still trip due to historical error rate"

    async def test_high_concurrency_gate(self) -> None:
        gate = MCPSecurityGate(allow_unverified_tokens=True)
        gate.rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

        results: list[str] = []

        async def make_request(idx: int) -> None:
            result = gate.check(
                tool_name="read_file",
                trust_level=MCPTrustLevel.UNTRUSTED,
                args={"path": "/tmp/test.txt"},
                context=ZeroTrustContext(agent_id=f"agent-{idx}"),
            )
            results.append(result)

        tasks = [make_request(i) for i in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)

        allowed = sum(1 for r in results if r == "ALLOW" or r == "AUDIT")
        denied = sum(1 for r in results if r == "DENY")

        assert denied > 0, f"Rate limiter should block some of {len(results)} requests (allowed={allowed}, denied={denied})"
        assert allowed <= 10, f"At most 10 requests should be allowed, got {allowed}"
        assert allowed + denied == len(results), f"All requests should have a verdict, got {len(results)} results"

    async def test_boundary_risk_scores(self) -> None:
        gate = MCPSecurityGate(allow_unverified_tokens=True)

        empty_trust = gate._calculate_risk(
            tool_name="",
            trust_level=MCPTrustLevel.UNTRUSTED,
            args={},
            context=ZeroTrustContext(agent_id=""),
        )
        assert isinstance(empty_trust, float), f"Expected float, got {type(empty_trust)}"
        assert 0.0 <= empty_trust <= 1.0, f"Risk score should be 0-1, got {empty_trust}"

        deep_delegation = gate._calculate_risk(
            tool_name="read_file",
            trust_level=MCPTrustLevel.SEMI_TRUSTED,
            args={},
            context=ZeroTrustContext(agent_id="test", delegation_depth=10),
        )
        assert isinstance(deep_delegation, float)
        assert deep_delegation >= 0.3, f"Deep delegation should increase risk score, got {deep_delegation}"

        dangerous_tool = gate._calculate_risk(
            tool_name="bash",
            trust_level=MCPTrustLevel.TRUSTED,
            args={"command": "ls"},
            context=ZeroTrustContext(agent_id="test"),
        )
        assert isinstance(dangerous_tool, float)
        assert dangerous_tool >= 0.0

    async def test_metrics_collector_under_load(self) -> None:
        collector = GuardrailMetricsCollector()

        start = time.time()
        for i in range(100):
            collector.record_check(
                verdict="DENY" if i % 3 == 0 else "ALLOW",
                gate="security" if i % 2 == 0 else "policy",
                duration_ms=10.0 + (i % 10) * 5,
            )
        elapsed = time.time() - start
        assert elapsed < 2.0, f"100 records should complete in < 2s, took {elapsed:.2f}s"

        stats = collector.get_stats()
        assert stats["total_checks"] == 100
        assert stats["deny_rate"] > 0
        assert stats["allow_rate"] > 0

        events = collector.get_recent_events(limit=10)
        assert len(events) == 10

    async def test_rate_limiter_edge_cases(self) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        allowed = sum(1 for _ in range(5) if limiter.check_rate())
        assert allowed == 5, f"Should allow exactly 5 requests, got {allowed}"

        assert not limiter.check_rate(), "6th request should be denied"

        current = limiter.get_current_rate()
        assert current == 5, f"Current rate should be 5, got {current}"

    async def test_empty_args_dont_crash(self) -> None:
        gate = MCPSecurityGate(allow_unverified_tokens=True)

        for trust_level in MCPTrustLevel:
            for tool in ["", None, "test"]:
                for args in [{}, None, {"": ""}]:
                    try:
                        gate.check(
                            tool_name=tool or "",
                            trust_level=trust_level,
                            args=args or {},
                            context=ZeroTrustContext(agent_id="test"),
                        )
                    except Exception as exc:
                        pytest.fail(f"Crash with trust={trust_level}, tool={tool}, args={args}: {exc}")

    async def test_concurrent_risk_score_updates(self) -> None:
        collector = GuardrailMetricsCollector()

        for i in range(50):
            collector.record_risk_score(f"agent-{i}", float(i * 10))

        stats = collector.get_stats()
        assert len(stats["risk_scores"]) == 50
        scores = {rs["agent_id"]: rs["score"] for rs in stats["risk_scores"]}
        assert scores["agent-0"] == 0.0
        assert scores["agent-49"] == 100.0
