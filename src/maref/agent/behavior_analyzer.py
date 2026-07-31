#!/usr/bin/env python3
"""
Agent Behavior Analysis SDK — Agent 行为分析 SDK / 异常行为检测引擎

五步分析法:
  Step 1: 建立行为基线 (Baseline)
  Step 2: 采集行为数据 (Collection)
  Step 3: 检测异常模式 (Detection)
  Step 4: 关联分析 (Correlation)
  Step 5: 生成洞察报告 (Report)

异常检测模式:
  - Decision Acceleration — 决策加速
  - Tool Abuse — 工具滥用
  - Rollback Storm — 回退风暴
  - Behavior Drift — 行为漂移

用法:
    python3 scripts/behavior_analysis_sdk.py analyze <events.json>
    python3 scripts/behavior_analysis_sdk.py baseline <history.json>
    python3 scripts/behavior_analysis_sdk.py report <analysis.json>
    python3 scripts/behavior_analysis_sdk.py simulate   # 生成示例数据
"""

from __future__ import annotations

import json
import logging
import math
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] BA-SDK: %(message)s")
logger = logging.getLogger("behavior_analysis")

# ── 数据模型 ────────────────────────────────────────────────

@dataclass
class AgentEvent:
    """Agent 行为事件"""
    timestamp: str
    agent_id: str
    action: str
    duration_ms: float
    tools_used: list[str] = field(default_factory=list)
    decision: str = ""
    confidence: float = 0.0
    tokens_consumed: int = 0
    status: str = "success"  # success | failure | retry | timeout

    @classmethod
    def from_dict(cls, d: dict) -> AgentEvent:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BehaviorBaseline:
    """Agent 行为基线"""
    agent_id: str
    sampled_events: int = 0
    avg_duration_ms: float = 0.0
    std_duration_ms: float = 0.0
    avg_tools_per_call: float = 0.0
    std_tools_per_call: float = 0.0
    success_rate: float = 1.0
    retry_rate: float = 0.0
    avg_tokens_per_session: float = 0.0
    daily_call_volume: float = 0.0
    top_actions: dict = field(default_factory=dict)
    top_tools: dict = field(default_factory=dict)
    built_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anomaly:
    anomaly_type: str       # acceleration | tool_abuse | rollback_storm | drift
    severity: str           # critical | high | medium | low
    agent_id: str
    description: str
    metric_before: float = 0.0
    metric_after: float = 0.0
    deviation_pct: float = 0.0
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Step 1: 建立行为基线 ───────────────────────────────────

def build_baseline(events: list[AgentEvent]) -> BehaviorBaseline:
    """从历史事件建立行为基线"""
    if not events:
        return BehaviorBaseline(agent_id="unknown", built_at=datetime.now(timezone.utc).isoformat())

    agent_id = events[0].agent_id
    n = len(events)

    durations = [e.duration_ms for e in events if e.duration_ms > 0]
    avg_dur = sum(durations) / len(durations) if durations else 0
    std_dur = math.sqrt(sum((d - avg_dur) ** 2 for d in durations) / len(durations)) if durations else 0

    tools_per = [len(e.tools_used) for e in events]
    avg_tools = sum(tools_per) / len(tools_per) if tools_per else 0
    std_tools = math.sqrt(sum((t - avg_tools) ** 2 for t in tools_per) / len(tools_per)) if tools_per else 0

    successes = sum(1 for e in events if e.status == "success")
    retries = sum(1 for e in events if e.status == "retry")

    tokens = [e.tokens_consumed for e in events if e.tokens_consumed > 0]
    avg_tokens = sum(tokens) / len(tokens) if tokens else 0

    actions = Counter(e.action for e in events)
    tools = Counter(t for e in events for t in e.tools_used)

    return BehaviorBaseline(
        agent_id=agent_id,
        sampled_events=n,
        avg_duration_ms=round(avg_dur, 1),
        std_duration_ms=round(std_dur, 1),
        avg_tools_per_call=round(avg_tools, 2),
        std_tools_per_call=round(std_tools, 2),
        success_rate=round(successes / n, 3) if n else 1.0,
        retry_rate=round(retries / n, 3) if n else 0.0,
        avg_tokens_per_session=round(avg_tokens, 1),
        daily_call_volume=round(n / 7, 1),  # assume 7 days of data
        top_actions=dict(actions.most_common(5)),
        top_tools=dict(tools.most_common(5)),
        built_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Step 2-3: 采集 + 检测异常 ─────────────────────────────

def detect_anomalies(events: list[AgentEvent], baseline: BehaviorBaseline | None = None) -> list[Anomaly]:
    """检测 Agent 行为异常"""
    if not events:
        return []

    if baseline is None:
        baseline = build_baseline(events)

    anomalies = []
    agent_id = events[0].agent_id

    # 按时间分窗口 (前50% vs 后50%)
    mid = len(events) // 2
    first_half = events[:mid]
    second_half = events[mid:]

    if not first_half or not second_half:
        return []

    # ── 1. Decision Acceleration — 决策加速 ──
    f_avg = sum(e.duration_ms for e in first_half) / len(first_half)
    s_avg = sum(e.duration_ms for e in second_half) / len(second_half)
    if f_avg > 0:
        deviation = (f_avg - s_avg) / f_avg * 100
        if deviation > 30:  # 下降超过 30%
            sev = "critical" if deviation > 50 else ("high" if deviation > 40 else "medium")
            anomalies.append(Anomaly(
                anomaly_type="acceleration",
                severity=sev,
                agent_id=agent_id,
                description=f"平均决策时间下降 {deviation:.1f}% ({f_avg:.0f}ms → {s_avg:.0f}ms)",
                metric_before=f_avg,
                metric_after=s_avg,
                deviation_pct=round(deviation, 1),
                recommendation="检查 Agent 是否跳过了关键推理步骤",
            ))

    # ── 2. Tool Abuse — 工具滥用 ──
    f_tools = [t for e in first_half for t in e.tools_used]
    s_tools = [t for e in second_half for t in e.tools_used]
    if f_tools:
        top_f = Counter(f_tools).most_common(1)[0][1] / len(first_half)
        top_s = Counter(s_tools).most_common(1)[0][1] / len(second_half) if s_tools else 0
        if top_f > 0 and top_s > top_f * 2:
            anomalies.append(Anomaly(
                anomaly_type="tool_abuse",
                severity="high",
                agent_id=agent_id,
                description=f"工具 {Counter(s_tools).most_common(1)[0][0]} 调用频率翻倍",
                metric_before=top_f,
                metric_after=top_s,
                deviation_pct=round((top_s - top_f) / top_f * 100, 1),
                recommendation="检查 Agent 是否陷入工具调用循环",
            ))

    # ── 3. Rollback Storm — 回退风暴 ──
    f_retries = sum(1 for e in first_half if e.status == "retry")
    s_retries = sum(1 for e in second_half if e.status == "retry")
    f_rate = f_retries / len(first_half)
    s_rate = s_retries / len(second_half)
    if f_rate > 0 and s_rate > f_rate * 2 and s_rate > 0.1:
        anomalies.append(Anomaly(
            anomaly_type="rollback_storm",
            severity="critical",
            agent_id=agent_id,
            description=f"回退率从 {f_rate*100:.1f}% 升至 {s_rate*100:.1f}%",
            metric_before=f_rate,
            metric_after=s_rate,
            deviation_pct=round((s_rate - f_rate) / f_rate * 100, 1),
            recommendation="检查 Agent 是否遇到无法处理的输入或系统故障",
        ))

    # ── 4. Behavior Drift — 行为漂移 ──
    if baseline.std_duration_ms > 0:
        recent = events[-min(20, len(events)):]
        recent_avg = sum(e.duration_ms for e in recent) / len(recent)
        z_score = (recent_avg - baseline.avg_duration_ms) / max(baseline.std_duration_ms, 1)
        if abs(z_score) > 2.0:
            anomalies.append(Anomaly(
                anomaly_type="drift",
                severity="high" if abs(z_score) > 3.0 else "medium",
                agent_id=agent_id,
                description=f"行为漂移检测: z-score={z_score:.2f} (阈值±2σ)",
                metric_before=baseline.avg_duration_ms,
                metric_after=recent_avg,
                deviation_pct=round(abs(z_score) * 10, 1),
                recommendation="最近 20 个事件偏离基线超过 2σ，建议审查 Agent 配置",
            ))

    return anomalies


# ── Step 4-5: 关联分析 + 生成报告 ─────────────────────────

def generate_report(events: list[AgentEvent], baseline: BehaviorBaseline,
                    anomalies: list[Anomaly]) -> dict:
    """生成完整行为分析报告"""
    # 异常关联分析
    anomaly_types = Counter(a.anomaly_type for a in anomalies)
    severity_counts = Counter(a.severity for a in anomalies)

    # 风险评分
    severity_scores = {"critical": 10, "high": 6, "medium": 3, "low": 1}
    risk_score = sum(severity_scores.get(a.severity, 0) for a in anomalies)

    # 报告
    report = {
        "report_id": f"ba-report-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": baseline.agent_id,
        "events_analyzed": len(events),
        "baseline": baseline.to_dict(),
        "anomalies_detected": len(anomalies),
        "risk_score": risk_score,
        "risk_level": "critical" if risk_score > 20 else ("high" if risk_score > 10 else ("medium" if risk_score > 5 else "low")),
        "anomaly_summary": {
            "by_type": dict(anomaly_types),
            "by_severity": dict(severity_counts),
        },
        "anomalies": [a.to_dict() for a in anomalies],
        "insights": [],
        "recommendations": [],
    }

    # 洞察和建议
    if any(a.anomaly_type == "acceleration" for a in anomalies):
        report["insights"].append("Agent 决策加速可能意味着它在偷工减料，跳过关键验证步骤")
        report["recommendations"].append("审查最近更新的 Agent 提示词和推理配置")

    if any(a.anomaly_type == "tool_abuse" for a in anomalies):
        report["insights"].append("工具调用频率异常可能表示 Agent 陷入了循环或低效状态")
        report["recommendations"].append("添加工具调用频率上限和循环检测机制")

    if any(a.anomaly_type == "rollback_storm" for a in anomalies):
        report["insights"].append("回退风暴表明 Agent 遇到了系统性障碍")
        report["recommendations"].append("检查最近的输入模式变化和外部依赖状态")

    if any(a.anomaly_type == "drift" for a in anomalies):
        report["insights"].append("行为漂移意味着 Agent 正在偏离初始设定，可能是隐式学习的结果")
        report["recommendations"].append("考虑重置 Agent 状态，审查 RSI 收敛阈值")

    if not anomalies:
        report["insights"].append("未检测到异常行为，Agent 运行正常")
        report["recommendations"].append("保持当前配置，定期（每周）重新评估基线")

    return report


# ── 示例数据生成 ───────────────────────────────────────────

def generate_sample_events(agent_id: str = "agent-ghost-001", n: int = 100) -> list[AgentEvent]:
    """生成模拟 Agent 行为数据用于测试"""
    actions = ["code_review", "file_read", "search", "analyze", "summarize", "generate"]
    tools = ["read_file", "search_code", "git_diff", "linter", "doc_gen"]
    decisions = ["approve", "reject", "modify", "defer"]

    events = []
    base_time = datetime.now(timezone.utc) - timedelta(days=7)

    for i in range(n):
        # Normal behavior
        is_abnormal = i > n * 0.8  # last 20% show anomalies
        if is_abnormal:
            dur = random.gauss(50, 20)  # much faster = acceleration
            t_used = random.choices(tools, k=random.randint(3, 6)) if random.random() < 0.7 else random.choices(tools, k=random.randint(1, 2))
            status = random.choices(["success", "retry", "failure"], weights=[0.5, 0.4, 0.1])[0]
        else:
            dur = random.gauss(350, 80)
            t_used = random.choices(tools, k=random.randint(1, 3))
            status = random.choices(["success", "retry", "failure"], weights=[0.9, 0.08, 0.02])[0]

        events.append(AgentEvent(
            timestamp=(base_time + timedelta(hours=i * 2)).isoformat(),
            agent_id=agent_id,
            action=random.choice(actions),
            duration_ms=max(10, dur),
            tools_used=t_used,
            decision=random.choice(decisions),
            confidence=round(random.uniform(0.7, 0.99), 2),
            tokens_consumed=random.randint(500, 5000),
            status=status,
        ))

    return events


# ── CLI ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "simulate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        agent = sys.argv[3] if len(sys.argv) > 3 else "agent-ghost-001"
        events = generate_sample_events(agent, n)
        output = f"ba-events-{agent}.json"
        with open(output, "w") as f:
            json.dump([e.to_dict() for e in events], f, ensure_ascii=False, indent=2)
        print(f"✅ 生成 {n} 条模拟事件 → {output}")

    elif cmd == "analyze":
        input_file = sys.argv[2] if len(sys.argv) > 2 else "ba-events-agent-ghost-001.json"
        try:
            with open(input_file) as f:
                raw = json.load(f)
            events = [AgentEvent.from_dict(e) for e in raw]

            # Step 1: Baseline
            baseline = build_baseline(events)
            print(f"\n📊 行为基线 [{baseline.agent_id}]")
            print(f"  采样: {baseline.sampled_events} 事件")
            print(f"  平均决策时间: {baseline.avg_duration_ms:.0f}ms (±{baseline.std_duration_ms:.0f}ms)")
            print(f"  成功率: {baseline.success_rate*100:.1f}%")
            print(f"  回退率: {baseline.retry_rate*100:.1f}%")

            # Step 2-3: Detect
            anomalies = detect_anomalies(events, baseline)
            if anomalies:
                print(f"\n🚨 检测到 {len(anomalies)} 个异常:")
                for a in anomalies:
                    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
                    print(f"  {sev_icon[a.severity]} [{a.anomaly_type}] {a.description}")
                    print(f"    → {a.recommendation}")
            else:
                print("\n✅ 未检测到异常行为")

            # Step 4-5: Report
            report = generate_report(events, baseline, anomalies)
            output = f"ba-report-{baseline.agent_id}.json"
            with open(output, "w") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"\n📄 报告已保存: {output}")

        except FileNotFoundError:
            print(f"❌ 文件不存在: {input_file}")
            print("   先用 'simulate' 生成示例数据")

    elif cmd == "report":
        report_file = sys.argv[2] if len(sys.argv) > 2 else "ba-report-agent-ghost-001.json"
        try:
            with open(report_file) as f:
                report = json.load(f)
            print(f"\n{'='*60}")
            print("  Agent 行为分析报告")
            print(f"  ID: {report['report_id']}")
            print(f"{'='*60}")
            print(f"  Agent: {report['agent_id']}")
            print(f"  分析事件: {report['events_analyzed']}")
            print(f"  风险评分: {report['risk_score']} ({report['risk_level']})")
            print(f"  异常数: {report['anomalies_detected']}")
            print()
            for insight in report["insights"]:
                print(f"  💡 {insight}")
            print()
            for rec in report["recommendations"]:
                print(f"  📋 {rec}")
        except FileNotFoundError:
            print(f"❌ 报告文件不存在: {report_file}")

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
