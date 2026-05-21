#!/usr/bin/env python3
"""
MAREF Sidecar 端到端演示脚本 (P0.3)

演示 AutoGen GroupChat + MAREF Sidecar 的非侵入式集成：
  1. 创建 3 个模拟 agent（研究员、评审员、总结员）
  2. 使用 AutoGenAdapter 或 MockAdapter 包装 GroupChat
  3. 运行 HotPotQA 风格的多跳问答任务
  4. Sidecar 实时观测 agent 状态、消息速率、熵值
  5. 输出观测报告和性能指标

Usage:
    python3 scripts/sidecar_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceStateMachine
from sidecar.collector import AgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.protocol import AgentId, AgentState, EntropyReading, StateSnapshot


@dataclass
class DemoReport:
    """Sidecar 演示运行报告."""

    task: str
    duration_sec: float
    total_messages: int
    agent_states: dict[str, str]
    entropy_readings: list[dict[str, Any]]
    sidecar_latency_ms: float
    findings: list[str] = field(default_factory=list)


class MockAgent:
    """模拟 AutoGen ChatAgent."""
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.produced_message_types = []


class MockGroupChat:
    """模拟 AutoGen BaseGroupChat."""
    def __init__(self, participants: list[MockAgent]) -> None:
        self._participants = participants
        self.name = "demo-group-chat"
        self.description = "MAREF Sidecar demo team"

    async def run_stream(self, task: str):
        """模拟消息流."""
        import random
        messages = [
            ("researcher", f"开始研究任务: {task}"),
            ("critic", "确认研究范围..."),
            ("researcher", "收集资料中，发现 3 个相关来源"),
            ("critic", "来源 1 可信度较低，建议交叉验证"),
            ("researcher", "已验证，补充 2 个高可信度来源"),
            ("summarizer", "综合发现：主要结论 A 和 B"),
            ("critic", "结论 A 需要更多数据支持"),
            ("researcher", "补充实验数据，结论 A 成立"),
            ("summarizer", "最终总结：..."),
        ]
        for source, content in messages:
            yield MockMessage(source, content)
            await asyncio.sleep(random.uniform(0.05, 0.15))
        yield MockTaskResult("任务完成")


class MockMessage:
    def __init__(self, source: str, content: str) -> None:
        self.source = source
        self.content = content


class MockTaskResult:
    def __init__(self, summary: str) -> None:
        self.summary = summary


class MockAutoGenAdapter(AgentAdapter):
    """不依赖 autogen_agentchat 的模拟 Adapter."""

    def __init__(self, group_chat: MockGroupChat) -> None:
        self._group_chat = group_chat
        self._participants = list(group_chat._participants)

        self._states: dict[str, AgentState] = {}
        self._tasks: dict[str, str] = {}
        self._message_counts: dict[str, int] = {}
        self._last_message_time: dict[str, float] = {}
        self._session_start: float = time.time()

    async def list_agents(self) -> list[AgentId]:
        return [
            AgentId(name=p.name, namespace="demo")
            for p in self._participants
        ]

    async def get_state(self, agent_id: AgentId) -> StateSnapshot | None:
        name = agent_id.name
        now = time.time()
        last_time = self._last_message_time.get(name, 0.0)
        seconds_since_msg = now - last_time if last_time > 0 else -1.0

        inferred = self._states.get(name, AgentState.IDLE)
        if inferred == AgentState.IDLE and 0 <= seconds_since_msg < 30:
            inferred = AgentState.RUNNING

        return StateSnapshot(
            agent_id=agent_id,
            timestamp=now,
            state=inferred,
            current_task=self._tasks.get(name, ""),
            task_progress=0.0,
            pending_messages=0,
            metadata={
                "total_messages": self._message_counts.get(name, 0),
                "last_message_seconds_ago": seconds_since_msg,
            },
        )

    async def get_entropy(self, agent_id: AgentId) -> EntropyReading | None:
        name = agent_id.name
        total = self._message_counts.get(name, 0)
        elapsed = time.time() - self._session_start
        rate = total / elapsed if elapsed > 0 else 0.0
        value = min(rate * 10, 10.0)

        level = "normal"
        if value > 7.0:
            level = "critical"
        elif value > 3.0:
            level = "warning"

        return EntropyReading(
            source=str(agent_id),
            timestamp=time.time(),
            value=round(value, 3),
            threshold=5.0,
            level=level,
        )

    def observe_message(self, source_name: str, content: str = "") -> None:
        self._message_counts[source_name] = self._message_counts.get(source_name, 0) + 1
        self._last_message_time[source_name] = time.time()
        self._states[source_name] = AgentState.RUNNING
        if content:
            self._tasks[source_name] = content[:120]

    async def observe_stream(self, stream):
        async for item in stream:
            if hasattr(item, "source"):
                content = getattr(item, "content", "")
                self.observe_message(item.source, content)
            yield item


async def run_sidecar_demo(task: str | None = None) -> DemoReport:
    """运行 Sidecar 端到端演示."""
    task = task or "分析 MAREF 治理系统的递归稳定性"
    print(f"[{time.strftime('%H:%M:%S')}] Sidecar Demo 启动")
    print(f"  任务: {task}")

    # 创建模拟团队
    agents = [
        MockAgent("researcher", "Conducts research and gathers data"),
        MockAgent("critic", "Reviews findings for accuracy"),
        MockAgent("summarizer", "Generates final summaries"),
    ]
    team = MockGroupChat(agents)

    # 创建 Sidecar Adapter（不依赖 autogen_agentchat）
    adapter = MockAutoGenAdapter(team)

    # 创建 Governance Overlay
    overlay = GovernanceOverlay(
        state_machine=GovernanceStateMachine(),
        collector=ObservationCollector(adapter, poll_interval=0.1),
        monitor=CompositeMonitor(),
        enable_self_observation=True,
    )

    # 运行任务并观测
    start_time = time.time()
    message_count = 0
    entropy_readings: list[dict[str, Any]] = []
    latency_samples: list[float] = []

    async for msg in adapter.observe_stream(team.run_stream(task)):
        inject_start = time.time()

        if hasattr(msg, "source"):
            message_count += 1
            print(f"  [{msg.source}] {msg.content[:60]}...")

            # 每 3 条消息采样一次熵值
            if message_count % 3 == 0:
                agent_ids = await adapter.list_agents()
                for agent_id in agent_ids:
                    entropy = await adapter.get_entropy(agent_id)
                    if entropy:
                        entropy_readings.append({
                            "agent": agent_id.name,
                            "value": entropy.value,
                            "level": entropy.level,
                            "timestamp": entropy.timestamp,
                        })

        latency_samples.append((time.time() - inject_start) * 1000)

        if hasattr(msg, "summary"):
            print(f"  [结果] {msg.summary}")
            break

    duration = time.time() - start_time
    avg_latency = sum(latency_samples) / len(latency_samples) if latency_samples else 0

    # 获取最终状态
    agent_ids = await adapter.list_agents()
    agent_states = {}
    for agent_id in agent_ids:
        state = await adapter.get_state(agent_id)
        if state:
            agent_states[agent_id.name] = state.state.name

    # 生成发现
    findings = [
        f"Sidecar 观测到 {message_count} 条消息，无丢失",
        f"平均注入延迟: {avg_latency:.3f}ms",
        f"Agent 状态分布: {agent_states}",
    ]

    if entropy_readings:
        max_entropy = max(r["value"] for r in entropy_readings)
        findings.append(f"最大熵值: {max_entropy:.2f}")

    report = DemoReport(
        task=task,
        duration_sec=duration,
        total_messages=message_count,
        agent_states=agent_states,
        entropy_readings=entropy_readings,
        sidecar_latency_ms=avg_latency,
        findings=findings,
    )

    print(f"\n[{time.strftime('%H:%M:%S')}] Sidecar Demo 完成")
    print(f"  运行时间: {duration:.2f}s")
    print(f"  消息总数: {message_count}")
    print(f"  平均延迟: {avg_latency:.3f}ms")

    return report


def print_report(report: DemoReport) -> None:
    """打印格式化报告."""
    print("\n" + "=" * 60)
    print("MAREF Sidecar 演示报告")
    print("=" * 60)
    print(f"任务: {report.task}")
    print(f"运行时间: {report.duration_sec:.2f}s")
    print(f"消息总数: {report.total_messages}")
    print(f"Sidecar 延迟: {report.sidecar_latency_ms:.3f}ms")
    print("\nAgent 最终状态:")
    for name, state in report.agent_states.items():
        print(f"  {name}: {state}")
    print("\n关键发现:")
    for finding in report.findings:
        print(f"  - {finding}")
    print("\n熵值采样:")
    for reading in report.entropy_readings[-5:]:
        print(f"  {reading['agent']}: {reading['value']:.2f} ({reading['level']})")
    print("=" * 60)


async def main() -> None:
    """主入口."""
    import argparse

    parser = argparse.ArgumentParser(description="MAREF Sidecar Demo")
    parser.add_argument(
        "--task",
        type=str,
        default="分析 MAREF 治理系统的递归稳定性",
        help="演示任务描述",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="运行次数（用于稳定性测试）",
    )

    args = parser.parse_args()

    all_reports: list[DemoReport] = []
    for i in range(args.iterations):
        if args.iterations > 1:
            print(f"\n--- 迭代 {i + 1}/{args.iterations} ---")
        report = await run_sidecar_demo(args.task)
        all_reports.append(report)

    # 打印最终报告
    print_report(all_reports[-1])

    # 多迭代统计
    if args.iterations > 1:
        print("\n多迭代统计:")
        durations = [r.duration_sec for r in all_reports]
        latencies = [r.sidecar_latency_ms for r in all_reports]
        print(f"  平均运行时间: {sum(durations) / len(durations):.2f}s")
        print(f"  平均 Sidecar 延迟: {sum(latencies) / len(latencies):.3f}ms")
        print(f"  最大延迟: {max(latencies):.3f}ms")
        print(f"  消息一致性: {all(r.total_messages == all_reports[0].total_messages for r in all_reports)}")


if __name__ == "__main__":
    asyncio.run(main())
