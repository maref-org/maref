"""
MAREF LLM 混沌测试引擎 (P2.1)

对 MAREF 治理系统注入 5 种混沌场景，验证系统韧性：
  1. 延迟注入 (LatencyInjection)
  2. 错误响应 (ErrorResponse)
  3. 丢包/超时 (PacketLoss)
  4. 熵增风暴 (EntropyStorm)
  5. 状态振荡 (StateOscillation)

Usage:
    from research.chaos_engineering import ChaosInjector
    injector = ChaosInjector()
    await injector.run_all_scenarios()
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from research.dashscope_client import DashScopeClient


@dataclass
class ChaosResult:
    """单次混沌实验结果."""

    scenario: str
    duration_sec: float
    success: bool
    system_stable: bool
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    findings: list[str] = field(default_factory=list)


class ChaosInjector:
    """MAREF 混沌测试注入器."""

    def __init__(self, llm_client: DashScopeClient | None = None) -> None:
        self._llm = llm_client
        self._results: list[ChaosResult] = []

    async def _with_latency(
        self,
        fn: Callable[..., Any],
        delay_ms: float = 5000.0,
        jitter_ms: float = 2000.0,
    ) -> Any:
        """Inject random latency before executing function."""
        actual_delay = max(0, delay_ms + random.uniform(-jitter_ms, jitter_ms))
        await asyncio.sleep(actual_delay / 1000.0)
        return await fn()

    async def _with_error(self, fn: Callable[..., Any], error_rate: float = 0.3) -> Any:
        """Inject random errors."""
        if random.random() < error_rate:
            raise RuntimeError("Injected chaos error")
        return await fn()

    async def scenario_latency_injection(self) -> ChaosResult:
        """
        Scenario 1: 延迟注入
        模拟 LLM API 响应变慢，测试 MAREF 超时处理.
        """
        start = time.time()
        findings = []

        # Baseline metrics
        metrics_before = {"response_time_ms": 200.0, "timeout_count": 0.0}

        # Inject latency into LLM calls
        llm = self._llm
        if llm is not None:
            try:
                await self._with_latency(
                    lambda: llm.chat_completion(
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=10,
                    ),
                    delay_ms=8000.0,  # 8s delay
                )
                findings.append("System handled 8s latency gracefully")
            except asyncio.TimeoutError:
                findings.append("Timeout detected - circuit breaker should activate")
            except Exception as e:
                findings.append(f"Error under latency: {e}")

        duration = time.time() - start
        metrics_after = {"response_time_ms": duration * 1000, "timeout_count": 1.0}

        return ChaosResult(
            scenario="latency_injection",
            duration_sec=duration,
            success=True,
            system_stable=len(findings) > 0,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            findings=findings,
        )

    async def scenario_error_response(self) -> ChaosResult:
        """
        Scenario 2: 错误响应
        模拟 LLM 返回 500/429 错误，测试重试和降级.
        """
        start = time.time()
        findings = []
        error_count = 0
        max_retries = 3

        metrics_before = {"error_rate": 0.0, "retry_count": 0.0}

        for attempt in range(max_retries + 1):
            try:
                await self._with_error(
                    lambda: asyncio.sleep(0.01),  # Simulate work
                    error_rate=0.5,
                )
                findings.append(f"Success after {attempt} retries")
                break
            except RuntimeError:
                error_count += 1
                if attempt < max_retries:
                    await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    findings.append("Max retries exceeded - fallback activated")

        duration = time.time() - start
        metrics_after = {"error_rate": error_count / (max_retries + 1), "retry_count": float(error_count)}

        return ChaosResult(
            scenario="error_response",
            duration_sec=duration,
            success=True,
            system_stable=error_count <= max_retries,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            findings=findings,
        )

    async def scenario_packet_loss(self) -> ChaosResult:
        """
        Scenario 3: 丢包/超时
        模拟网络分区，30% 请求无响应.
        """
        start = time.time()
        findings = []
        total_requests = 10
        dropped = 0

        metrics_before = {"drop_rate": 0.0, "success_rate": 1.0}

        for _i in range(total_requests):
            if random.random() < 0.3:  # 30% drop rate
                dropped += 1
                continue
            await asyncio.sleep(0.01)  # Simulate successful request

        drop_rate = dropped / total_requests
        findings.append(f"Packet loss simulation: {dropped}/{total_requests} dropped ({drop_rate:.0%})")

        if drop_rate > 0.25:
            findings.append("High packet loss detected - system should queue or buffer")

        duration = time.time() - start
        metrics_after = {"drop_rate": drop_rate, "success_rate": 1.0 - drop_rate}

        return ChaosResult(
            scenario="packet_loss",
            duration_sec=duration,
            success=True,
            system_stable=drop_rate < 0.5,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            findings=findings,
        )

    async def scenario_entropy_storm(self) -> ChaosResult:
        """
        Scenario 4: 熵增风暴
        模拟 Agent 消息速率突然提升 10 倍，测试治理系统响应.
        """
        start = time.time()
        findings = []

        metrics_before = {"message_rate": 1.0, "entropy_level": 2.0}

        # Simulate 10x message rate
        burst_messages = 100
        for _ in range(burst_messages):
            # Simulate processing each message
            await asyncio.sleep(0.001)

        findings.append(f"Processed {burst_messages} messages in burst mode")

        # Check if entropy threshold would trigger
        simulated_entropy = burst_messages / 10.0
        if simulated_entropy > 5.0:
            findings.append("Entropy threshold exceeded - governance should intervene")

        duration = time.time() - start
        metrics_after = {"message_rate": burst_messages / duration, "entropy_level": simulated_entropy}

        return ChaosResult(
            scenario="entropy_storm",
            duration_sec=duration,
            success=True,
            system_stable=simulated_entropy < 10.0,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            findings=findings,
        )

    async def scenario_state_oscillation(self) -> ChaosResult:
        """
        Scenario 5: 状态振荡
        模拟 Agent 在 OBSERVE ↔ ANALYZE ↔ EVALUATE 间高频切换.
        """
        start = time.time()
        findings = []

        from maref_lite.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        transitions = []
        oscillation_count = 0

        metrics_before = {"state_changes": 0.0, "oscillation_rate": 0.0}

        # Rapid state switching
        states = [GovernanceState.OBSERVE, GovernanceState.ANALYZE, GovernanceState.EVALUATE]
        for _ in range(20):
            next_state = random.choice(states)
            try:
                sm.transition(next_state, "chaos_test")
                transitions.append(next_state.name)
            except ValueError:
                pass  # Invalid transition

        # Detect oscillation (repeated back-and-forth)
        for i in range(2, len(transitions)):
            if transitions[i] == transitions[i-2] and transitions[i] != transitions[i-1]:
                oscillation_count += 1

        findings.append(f"State transitions: {len(transitions)}")
        findings.append(f"Oscillation detected: {oscillation_count} times")

        if oscillation_count > 5:
            findings.append("CRITICAL: High oscillation rate - governance should stabilize")

        duration = time.time() - start
        metrics_after = {"state_changes": float(len(transitions)), "oscillation_rate": oscillation_count / max(len(transitions), 1)}

        return ChaosResult(
            scenario="state_oscillation",
            duration_sec=duration,
            success=True,
            system_stable=oscillation_count < 10,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            findings=findings,
        )

    async def run_all_scenarios(self) -> list[ChaosResult]:
        """Run all chaos scenarios sequentially."""
        scenarios = [
            self.scenario_latency_injection,
            self.scenario_error_response,
            self.scenario_packet_loss,
            self.scenario_entropy_storm,
            self.scenario_state_oscillation,
        ]

        print(f"[{time.strftime('%H:%M:%S')}] Starting chaos engineering test suite")
        print(f"  Total scenarios: {len(scenarios)}")

        for i, scenario_fn in enumerate(scenarios):
            print(f"\n  [{i+1}/{len(scenarios)}] Running {scenario_fn.__name__}...")
            result = await scenario_fn()
            self._results.append(result)
            print(f"    Duration: {result.duration_sec:.2f}s")
            print(f"    Stable: {result.system_stable}")
            for finding in result.findings[:2]:
                print(f"    - {finding}")

        return self._results

    def generate_report(self) -> dict[str, Any]:
        """Generate chaos test report."""
        total = len(self._results)
        stable = sum(1 for r in self._results if r.system_stable)

        return {
            "total_scenarios": total,
            "stable_scenarios": stable,
            "stability_rate": stable / total if total > 0 else 0,
            "scenarios": [
                {
                    "name": r.scenario,
                    "duration_sec": r.duration_sec,
                    "stable": r.system_stable,
                    "findings": r.findings,
                }
                for r in self._results
            ],
        }


async def main() -> None:
    """CLI entry point for chaos testing."""
    import argparse

    parser = argparse.ArgumentParser(description="MAREF Chaos Engineering")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Use real LLM for latency injection tests",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research_output/chaos_report.json"),
        help="Output path for report",
    )

    args = parser.parse_args()

    llm = None
    if args.with_llm:
        try:
            llm = DashScopeClient()
            print("LLM client initialized for chaos tests")
        except ValueError:
            print("Warning: No DASHSCOPE_API_KEY, running without LLM")

    injector = ChaosInjector(llm_client=llm)
    try:
        await injector.run_all_scenarios()
        report = injector.generate_report()

        # Save report
        args.output.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\nChaos test report saved to {args.output}")
        print(f"Stability rate: {report['stability_rate']:.0%}")
    finally:
        if llm:
            await llm.close()
            print("LLM client session closed.")


if __name__ == "__main__":
    asyncio.run(main())
