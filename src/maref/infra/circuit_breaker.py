#!/usr/bin/env python3
"""
Circuit Breaker + StuckDetector — Agent 自愈基础设施

三个保护层:
  1. ActionPatternTracker — 跟踪 tool call 签名，检测重复模式
  2. CircuitBreaker — 三档断路器 (warn / block / escalate)
  3. StuckDetector — 组合检测 + SQLite 持久化 + 健康报告

集成自 agent-guard-mcp 的设计模式，但深度适配 MAREF 现有架构:
  - 使用 state.py 的 OpenClawState 做持久化 (SQLite WAL)
  - 使用 loop/halting.py 的 HaltingCondition 策略模式
  - 使用 check_env.py 的风格做初始化

用法:
    from maref.infra.circuit_breaker import StuckDetector, BreakerLevel

    detector = StuckDetector("my-agent")
    detector.log_action("read_file", {"path": "foo.py"}, "found 42 lines")
    report = detector.analyze()
    if report["is_stuck"]:
        print(f"卡死风险 {report['confidence']:.0%}: {report['suggestion']}")
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("maref.circuit_breaker")

# ── 常量 ────────────────────────────────────────────────────

ROLLING_WINDOW = 50          # 每个 agent 保留最近 50 条 action 记录
DEFAULT_MAX_REPEATS = 3      # 相同签名重复 N 次触发警告
DEFAULT_PROGRESS_THRESHOLD = 0.3  # 多样性比率低于此值视为卡死
REPEAT_WINDOW = 10           # 在最近 10 次操作中检测重复
TOKEN_COST_PER_REDUNDANT = 500    # 每次冗余操作估算 token 消耗
COST_PER_TOKEN = 0.000003    # 估算每 token 成本 (USD)


class BreakerLevel(str, Enum):
    """Circuit breaker 三档动作。"""
    WARN = "warn"                     # 允许但警告
    BLOCK = "block"                   # 阻止执行
    ESCALATE = "escalate"             # 阻止 + 上报人类


class StuckPattern(str, Enum):
    """卡死模式分类。"""
    HEALTHY = "healthy"
    INSUFFICIENT_DATA = "insufficient_data"
    EXACT_REPEAT = "exact_repeat"
    LOW_DIVERSITY = "low_diversity"
    EXACT_REPEAT_AND_LOW_DIVERSITY = "exact_repeat_and_low_diversity"


# ── 数据结构 ────────────────────────────────────────────────


@dataclass
class ActionRecord:
    """一次 tool call 的记录。"""
    tool_name: str
    args: dict[str, Any]
    signature: str = ""
    result_preview: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.signature:
            self.signature = self._hash_args(self.args)
        if not self.timestamp:
            self.timestamp = time.time()

    @staticmethod
    def _hash_args(args: dict[str, Any]) -> str:
        """生成确定性签名: tool_name + 排序后的参数哈希。"""
        raw = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @property
    def sig_key(self) -> str:
        """完整签名键 (tool_name + args_hash)。"""
        return f"{self.tool_name}:{self.signature}"


@dataclass
class BreakerConfig:
    """断路器的配置。"""
    max_repeats: int = DEFAULT_MAX_REPEATS
    level: BreakerLevel = BreakerLevel.WARN


@dataclass
class StuckReport:
    """卡死分析报告。"""
    is_stuck: bool = False
    confidence: float = 0.0
    pattern: str = StuckPattern.HEALTHY.value
    suggestion: str = "Agent 正常运行，无需干预。"
    repeated_actions: list[dict[str, Any]] = field(default_factory=list)
    total_actions: int = 0
    unique_signatures: int = 0
    diversity_ratio: float = 1.0
    redundant_actions: int = 0
    estimated_token_waste: int = 0
    estimated_cost_waste_usd: float = 0.0
    breaker_triggered: bool = False
    breaker_level: str = ""
    recent_timeline: list[dict[str, Any]] = field(default_factory=list)


# ── Action Pattern Tracker ──────────────────────────────────


class ActionPatternTracker:
    """跟踪 agent 的 tool call 模式，检测重复。

    与 agent-guard-mcp 不同的设计:
      - 直接使用 OpenClawState 做持久化 (不额外引入 SQLite)
      - 集成 MAREF 现有的 agent 命名空间
      - 支持内存模式和持久化模式
    """

    def __init__(
        self,
        agent_id: str,
        progress_threshold: float = DEFAULT_PROGRESS_THRESHOLD,
        use_persistence: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.progress_threshold = progress_threshold
        self._use_persistence = use_persistence
        self._state = None
        self._memory: list[ActionRecord] = []

        if use_persistence:
            try:
                from maref.infra.state import OpenClawState
                self._state = OpenClawState(f"cb_{agent_id}")
            except ImportError:
                logger.warning("OpenClawState 不可用，回退到内存模式")
                self._use_persistence = False

        logger.debug(
            "ActionPatternTracker[%s] 初始化 (persist=%s, threshold=%.2f)",
            agent_id, use_persistence, progress_threshold,
        )

    def log_action(
        self,
        tool_name: str,
        args: dict[str, Any],
        result_preview: str = "",
    ) -> dict[str, Any]:
        """记录一次 tool call，返回警告信息（如有重复模式）。"""
        record = ActionRecord(
            tool_name=tool_name,
            args=args,
            result_preview=result_preview[:200],
        )
        self._memory.append(record)

        # 持久化
        if self._use_persistence and self._state:
            self._persist_action(record)

        # 滚动窗口：只保留最近 ROLLING_WINDOW 条
        if len(self._memory) > ROLLING_WINDOW:
            self._memory = self._memory[-ROLLING_WINDOW:]

        # 快速检测：最近 REPEAT_WINDOW 次操作中是否有重复模式
        return self._quick_check()

    def _persist_action(self, record: ActionRecord) -> None:
        """将 action 持久化到 OpenClawState。"""
        if not self._state:
            return
        actions = self._state.get("action_log", [])
        actions.append({
            "tool_name": record.tool_name,
            "signature": record.signature,
            "sig_key": record.sig_key,
            "result_preview": record.result_preview,
            "timestamp": record.timestamp,
        })
        # 滚动窗口
        if len(actions) > ROLLING_WINDOW:
            actions = actions[-ROLLING_WINDOW:]
        self._state.set("action_log", actions)

    def _quick_check(self) -> dict[str, Any]:
        """对最近 REPEAT_WINDOW 条记录做快速重复检测。"""
        recent = self._memory[-REPEAT_WINDOW:]
        sig_counts: dict[str, int] = {}
        for r in recent:
            sig_counts[r.sig_key] = sig_counts.get(r.sig_key, 0) + 1

        max_repeat = max(sig_counts.values()) if sig_counts else 0
        warning = None
        if max_repeat >= DEFAULT_MAX_REPEATS:
            repeated_sig = next(
                (k for k, v in sig_counts.items() if v >= DEFAULT_MAX_REPEATS),
                None,
            )
            warning = (
                f"Action \"{repeated_sig}\" 重复 {max_repeat} 次 "
                f"(最近 {REPEAT_WINDOW} 次操作中) — 可能进入循环"
            )

        return {
            "total_logged": len(self._memory),
            "recent_window": len(recent),
            "max_repeat_in_window": max_repeat,
            "warning": warning,
        }

    def get_history(self) -> list[ActionRecord]:
        """返回当前 tracker 中的所有记录。"""
        return list(self._memory)

    def clear(self) -> None:
        """清空跟踪记录。"""
        self._memory.clear()
        if self._use_persistence and self._state:
            self._state.delete("action_log")


# ── Circuit Breaker ─────────────────────────────────────────


class CircuitBreaker:
    """三档断路器: warn → block → escalate。

    与 agent-guard-mcp 对齐:
      - warn: 允许执行但记录警告
      - block: 阻止执行 (返回 blocked=True)
      - escalate: 阻止 + 标记需人工介入
    """

    def __init__(
        self,
        agent_id: str,
        max_repeats: int = DEFAULT_MAX_REPEATS,
        level: BreakerLevel = BreakerLevel.WARN,
        use_persistence: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.max_repeats = max_repeats
        self.level = level
        self._use_persistence = use_persistence
        self._state = None

        if use_persistence:
            try:
                from maref.infra.state import OpenClawState
                self._state = OpenClawState(f"cb_{agent_id}")
                saved = self._state.get("breaker_config")
                if saved:
                    self.max_repeats = saved.get("max_repeats", max_repeats)
                    self.level = BreakerLevel(saved.get("level", level.value))
            except ImportError:
                self._use_persistence = False

    def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        recent_history: list[ActionRecord],
    ) -> dict[str, Any]:
        """检查此 tool call 是否应被断路器阻止。

        Args:
            tool_name: 即将调用的工具名
            args: 即将传递的参数
            recent_history: 最近的 action 历史

        Returns:
            {"proceed": bool, "reason": str, "suggestion": str | None}
        """
        # 计算提议调用的签名
        raw = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        proposed_hash = hashlib.sha256(raw.encode()).hexdigest()[:12]
        proposed_sig = f"{tool_name}:{proposed_hash}"

        # 统计此签名在历史中的出现次数
        times_seen = sum(1 for r in recent_history if r.sig_key == proposed_sig)

        if times_seen < self.max_repeats:
            return {
                "proceed": True,
                "reason": f"Action 已出现 {times_seen}/{self.max_repeats} 次 — 在限额内",
                "suggestion": None,
            }

        # 断路器触发
        tool_display = tool_name
        msg = f"\"{tool_display}\" 已用相同参数调用 {times_seen} 次 (限额: {self.max_repeats})"

        if self.level == BreakerLevel.BLOCK:
            return {
                "proceed": False,
                "reason": f"🔴 BLOCKED: {msg}",
                "suggestion": "请改用不同的参数、不同的工具，或者上报阻塞。",
            }

        if self.level == BreakerLevel.ESCALATE:
            return {
                "proceed": False,
                "reason": f"🚨 ESCALATED: {msg}",
                "suggestion": "此任务需要人工介入。记录已保存待审。",
            }

        # WARN (默认)
        return {
            "proceed": True,
            "reason": f"🟡 WARNING: {msg} — 可能进入无限循环",
            "suggestion": "建议修改参数或换用其他工具。",
        }

    def update_config(self, max_repeats: int | None = None, level: BreakerLevel | None = None) -> None:
        """动态更新断路器配置。"""
        if max_repeats is not None:
            self.max_repeats = max_repeats
        if level is not None:
            self.level = level
        if self._use_persistence and self._state:
            self._state.set("breaker_config", {
                "max_repeats": self.max_repeats,
                "level": self.level.value,
            })
        logger.info(
            "断路器 [%s] 配置更新: max_repeats=%d, level=%s",
            self.agent_id, self.max_repeats, self.level.value,
        )


# ── StuckDetector (组合检测器) ───────────────────────────────


class StuckDetector:
    """组合检测器: ActionPatternTracker + CircuitBreaker + 分析报告。

    这是对外的主要接口，整合三个保护层:
      1. 跟踪所有 action 并检测重复模式
      2. 断路器决定是否阻止
      3. 生成详细的分析报告和修复建议

    用法:
        detector = StuckDetector("flywheel")
        detector.log_action("read_file", {"path": "foo.py"})
        report = detector.analyze()
        if report["is_stuck"]:
            print(report["suggestion"])

    集成到 GuvernedLoop:
        from maref.loop.halting import StuckDetected
        loop.add_condition(StuckDetected(detector))
    """

    def __init__(
        self,
        agent_id: str,
        progress_threshold: float = DEFAULT_PROGRESS_THRESHOLD,
        breaker_max_repeats: int = DEFAULT_MAX_REPEATS,
        breaker_level: BreakerLevel = BreakerLevel.WARN,
        use_persistence: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.tracker = ActionPatternTracker(
            agent_id=agent_id,
            progress_threshold=progress_threshold,
            use_persistence=use_persistence,
        )
        self.breaker = CircuitBreaker(
            agent_id=agent_id,
            max_repeats=breaker_max_repeats,
            level=breaker_level,
            use_persistence=use_persistence,
        )

    def log_action(
        self,
        tool_name: str,
        args: dict[str, Any],
        result_preview: str = "",
    ) -> dict[str, Any]:
        """记录 action + 断路器预检。"""
        # 先检查断路器
        history = self.tracker.get_history()
        breaker_result = self.breaker.check(tool_name, args, history)

        # 记录 action
        check_result = self.tracker.log_action(tool_name, args, result_preview)

        return {
            "breaker": breaker_result,
            "pattern": check_result,
        }

    def check_before_action(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """在执行 tool call 前调用，检查是否被断路器阻止。"""
        history = self.tracker.get_history()
        return self.breaker.check(tool_name, args, history)

    def analyze(self) -> dict[str, Any]:
        """全面分析 agent 状态，生成 StuckReport。"""
        history = self.tracker.get_history()
        report = StuckReport()

        if len(history) < 3:
            report.is_stuck = False
            report.pattern = StuckPattern.INSUFFICIENT_DATA.value
            report.suggestion = f"数据不足 (仅 {len(history)} 条，需至少 3 条)"
            return dataclasses.asdict(report)

        # ── 分析最近 REPEAT_WINDOW 条 ──
        recent = history[-REPEAT_WINDOW:]
        sig_counts: dict[str, int] = {}
        for r in recent:
            sig_counts[r.sig_key] = sig_counts.get(r.sig_key, 0) + 1

        repeated = [
            {"signature": k, "count": v}
            for k, v in sorted(sig_counts.items(), key=lambda x: -x[1])
            if v >= 2
        ]

        max_repeat_in_window = max(sig_counts.values()) if sig_counts else 0
        repeat_exact = max_repeat_in_window >= DEFAULT_MAX_REPEATS

        # ── 多样性分析 ──
        all_signatures = [r.sig_key for r in history]
        unique_sigs = set(all_signatures)
        diversity_ratio = len(unique_sigs) / len(all_signatures) if all_signatures else 1.0
        low_diversity = diversity_ratio < self.tracker.progress_threshold

        # ── 卡死判定 ──
        is_stuck = repeat_exact or low_diversity
        if repeat_exact and low_diversity:
            pattern = StuckPattern.EXACT_REPEAT_AND_LOW_DIVERSITY
        elif repeat_exact:
            pattern = StuckPattern.EXACT_REPEAT
        elif low_diversity:
            pattern = StuckPattern.LOW_DIVERSITY
        else:
            pattern = StuckPattern.HEALTHY

        # ── 置信度 ──
        confidence = 0.0
        if repeat_exact:
            confidence = min(0.5 + (max_repeat_in_window - DEFAULT_MAX_REPEATS) * 0.15, 1.0)
        if low_diversity:
            confidence = max(confidence, 1.0 - diversity_ratio)

        # ── Token 浪费估算 ──
        redundant = len(all_signatures) - len(unique_sigs)
        token_waste = redundant * TOKEN_COST_PER_REDUNDANT
        cost_waste = token_waste * COST_PER_TOKEN

        # ── 建议 ──
        if is_stuck:
            top_repeated = str(repeated[0]["signature"]) if repeated else "unknown"
            tool_name_only = top_repeated.split(":")[0]
            suggestion = (
                f"Agent 反复调用 \"{tool_name_only}\" (相同参数 {max_repeat_in_window}/{REPEAT_WINDOW} 次)。"
                f"建议: (1) 换用不同参数 (2) 换工具 (3) 拆分子任务 (4) 上报阻塞。"
                f"已浪费约 {token_waste:,} tokens (${cost_waste:.4f})。"
            )
        else:
            suggestion = "Agent 正常推进，无需干预。"

        # ── 断路器状态 ──
        breaker_triggered = confidence >= 0.5
        timeline = [
            {
                "tool": r.tool_name,
                "preview": r.result_preview[:100] if r.result_preview else None,
                "time": r.timestamp,
            }
            for r in history[-20:]
        ]

        report.is_stuck = is_stuck
        report.confidence = round(confidence, 3)
        report.pattern = pattern.value
        report.suggestion = suggestion
        report.repeated_actions = repeated
        report.total_actions = len(history)
        report.unique_signatures = len(unique_sigs)
        report.diversity_ratio = round(diversity_ratio, 3)
        report.redundant_actions = redundant
        report.estimated_token_waste = token_waste
        report.estimated_cost_waste_usd = round(cost_waste, 4)
        report.breaker_triggered = breaker_triggered
        report.breaker_level = self.breaker.level.value if breaker_triggered else ""
        report.recent_timeline = timeline

        return dataclasses.asdict(report)

    def reset(self) -> None:
        """重置追踪器和断路器状态。"""
        self.tracker.clear()
        logger.info("StuckDetector [%s] 已重置", self.agent_id)


# ── 工具函数 ────────────────────────────────────────────────


def format_report(report: dict[str, Any]) -> str:
    """将 StuckReport 格式化为可读文本。"""
    lines = []
    lines.append(f"📊 Agent 卡死分析报告 — {report.get('total_actions', 0)} 次操作")
    lines.append(f"{'='*50}")
    lines.append(f"  状态:       {'🔴 卡死' if report['is_stuck'] else '✅ 正常'}")
    lines.append(f"  置信度:     {report.get('confidence', 0):.0%}")
    lines.append(f"  模式:       {report.get('pattern', 'unknown')}")
    lines.append(f"  多样性比率: {report.get('diversity_ratio', 1.0):.2f}")
    lines.append(f"  冗余操作:   {report.get('redundant_actions', 0)} 次")
    lines.append(f"  浪费 tokens: ~{report.get('estimated_token_waste', 0):,} (${report.get('estimated_cost_waste_usd', 0):.4f})")
    lines.append(f"  断路器:     {'触发' if report.get('breaker_triggered') else '未触发'}")
    lines.append("")
    lines.append(f"  建议: {report.get('suggestion', 'N/A')}")
    lines.append("")
    if report.get("repeated_actions"):
        lines.append("  重复模式 (Top):")
        for ra in report["repeated_actions"][:5]:
            lines.append(f"    - {ra['signature']}: {ra['count']} 次")
    return "\n".join(lines)


# ── CLI 测试 ────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Circuit Breaker CLI 测试")
    parser.add_argument("--agent", default="test-agent", help="Agent ID")
    parser.add_argument("--simulate-loop", action="store_true", help="模拟卡死循环")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    detector = StuckDetector(args.agent, breaker_level=BreakerLevel.WARN)

    if args.simulate_loop:
        print(f"🔄 模拟卡死循环 (agent={args.agent})...\n")
        for i in range(15):
            result = detector.log_action(
                "read_file",
                {"path": "same_file.txt"},
                "同样的内容",
            )
            if i < 3:
                print(f"  [{i+1}/15] 正常")
            else:
                print(f"  [{i+1}/15] {result['pattern']['warning'] or '正常'}")
            time.sleep(0.1)
        print()
        report = detector.analyze()
        print(format_report(report))
    else:
        # 正常模式测试
        for tool, args_dict in [
            ("read_file", {"path": "a.py"}),
            ("write_file", {"path": "b.py", "content": "..."}),
            ("read_file", {"path": "c.py"}),
            ("search", {"query": "foo"}),
            ("read_file", {"path": "d.py"}),
            ("write_file", {"path": "e.py", "content": "..."}),
        ]:
            detector.log_action(tool, args_dict)
        report = detector.analyze()
        print(format_report(report))
