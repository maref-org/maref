"""Loop Halting Conditions — strategy pattern for loop termination."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class HaltingContext:
    """Context passed to halting conditions for evaluation."""

    iteration: int
    elapsed_seconds: float
    state: dict[str, Any]
    errors: int
    converged: bool | None = None


class HaltingCondition(ABC):
    """Base class for loop halting conditions."""

    @abstractmethod
    def should_halt(self, ctx: HaltingContext) -> bool:
        ...

    @abstractmethod
    def reason(self) -> str:
        ...


class MaxIterations(HaltingCondition):
    """Halt after N iterations."""

    def __init__(self, max_iterations: int) -> None:
        self._max = max_iterations

    def should_halt(self, ctx: HaltingContext) -> bool:
        return ctx.iteration >= self._max

    def reason(self) -> str:
        return f"max_iterations({self._max})"


class Timeout(HaltingCondition):
    """Halt after T seconds of wall-clock time."""

    def __init__(self, max_seconds: float) -> None:
        self._max = max_seconds

    def should_halt(self, ctx: HaltingContext) -> bool:
        return ctx.elapsed_seconds >= self._max

    def reason(self) -> str:
        return f"timeout({self._max:.0f}s)"


class GoalAchieved(HaltingCondition):
    """Halt when a goal check function returns True."""

    def __init__(self, check_fn: Any, description: str = "goal_achieved") -> None:
        self._check = check_fn
        self._desc = description

    def should_halt(self, ctx: HaltingContext) -> bool:
        try:
            return bool(self._check(ctx.state))
        except Exception:
            return False

    def reason(self) -> str:
        return self._desc


class ConvergenceDetected(HaltingCondition):
    """Halt when state hasn't meaningfully changed for N iterations."""

    def __init__(self, threshold: float = 0.01, patience: int = 3) -> None:
        self._threshold = threshold
        self._patience = patience
        self._previous_state: dict[str, Any] | None = None
        self._stalled = 0
        self._reason_str = "convergence_detected"

    def should_halt(self, ctx: HaltingContext) -> bool:
        if self._previous_state is None:
            self._previous_state = dict(ctx.state)
            return False
        change = self._compute_change(self._previous_state, ctx.state)
        self._previous_state = dict(ctx.state)
        if change < self._threshold:
            self._stalled += 1
        else:
            self._stalled = 0
        if self._stalled >= self._patience:
            self._reason_str = f"converged(stalled={self._stalled}, change={change:.4f})"
            return True
        return False

    @staticmethod
    def _compute_change(old: dict[str, Any], new: dict[str, Any]) -> float:
        keys = set(old) & set(new)
        diffs = []
        for k in keys:
            if isinstance(old[k], (int, float)) and isinstance(new[k], (int, float)):
                diffs.append(abs(new[k] - old[k]))
        if not diffs:
            return 1.0
        return sum(diffs) / len(diffs)

    def reason(self) -> str:
        return self._reason_str


class Never(HaltingCondition):
    """Never halt — use with external stop() signal."""

    def should_halt(self, ctx: HaltingContext) -> bool:
        return False

    def reason(self) -> str:
        return "never"


class AnyOf(HaltingCondition):
    """Halt when ANY sub-condition is met."""

    def __init__(self, *conditions: HaltingCondition) -> None:
        self._conditions = conditions

    def should_halt(self, ctx: HaltingContext) -> bool:
        return any(c.should_halt(ctx) for c in self._conditions)

    def reason(self) -> str:
        triggered = [c.reason() for c in self._conditions]
        return f"any_of({', '.join(triggered)})"


class AllOf(HaltingCondition):
    """Halt when ALL sub-conditions are met."""

    def __init__(self, *conditions: HaltingCondition) -> None:
        self._conditions = conditions

    def should_halt(self, ctx: HaltingContext) -> bool:
        return all(c.should_halt(ctx) for c in self._conditions)

    def reason(self) -> str:
        return "all_of(" + ", ".join(c.reason() for c in self._conditions) + ")"


class SemanticConvergenceDetected(HaltingCondition):
    """语义收敛检测 — 让 Loop 框架具备语义感知。

    三条收敛路径（OR 关系，满足任一条即触发）:
    1. 概念漂移稳定: 最近 N 轮 mean_drift < drift_threshold
    2. 假设置信度饱和: best_confidence_delta < confidence_delta 持续 patience 轮
    3. 知识图谱健康: orphan_ratio < max_orphan_ratio 且 connected_components <= 1

    通过 HaltingContext.state 接收语义信号:
      state["mean_drift"]           — OntologyDriftDetector 的总体漂移值
      state["best_confidence"]      — 最高置信度的假设值
      state["orphan_ratio"]         — KG 孤儿节点占比
      state["connected_components"] — KG 连通分支数

    用法:
        # 在 SelfHealingLoop._run_one_cycle 之后:
        ctx.state["mean_drift"] = drift_detector.get_mean_drift()
        ctx.state["orphan_ratio"] = kg.get_connectivity_stats()["orphan_ratio"]
    """

    def __init__(
        self,
        drift_window: int = 3,
        drift_threshold: float = 0.01,
        confidence_delta: float = 0.02,
        patience: int = 3,
        max_orphan_ratio: float = 0.3,
    ) -> None:
        self._drift_window = drift_window
        self._drift_threshold = drift_threshold
        self._confidence_delta = confidence_delta
        self._patience = patience
        self._max_orphan_ratio = max_orphan_ratio

        self._drift_history: list[float] = []
        self._last_best_confidence: float | None = None
        self._confidence_stalled = 0
        self._reason_str = ""

    def should_halt(self, ctx: HaltingContext) -> bool:
        self._reason_str = ""  # 每次调用重置，避免跨周期残留
        state = ctx.state

        # ── Path 1: 概念漂移稳定 ──
        mean_drift = state.get("mean_drift")
        if mean_drift is not None and isinstance(mean_drift, (int, float)):
            self._drift_history.append(float(mean_drift))
            if len(self._drift_history) > self._drift_window:
                self._drift_history = self._drift_history[-self._drift_window :]

            if len(self._drift_history) >= self._drift_window:
                if all(d < self._drift_threshold for d in self._drift_history):
                    self._reason_str = (
                        f"semantic_converged(drift_stable={self._drift_history[-1]:.4f})"
                    )
                    return True

        # ── Path 2: 假设置信度饱和 ──
        best_conf = state.get("best_confidence")
        if best_conf is not None and isinstance(best_conf, (int, float)):
            if self._last_best_confidence is not None:
                delta = abs(float(best_conf) - self._last_best_confidence)
                if delta < self._confidence_delta:
                    self._confidence_stalled += 1
                else:
                    self._confidence_stalled = 0
                if self._confidence_stalled >= self._patience:
                    self._reason_str = (
                        f"semantic_converged(confidence_saturated={float(best_conf):.4f} "
                        f"stalled={self._confidence_stalled})"
                    )
                    return True
            self._last_best_confidence = float(best_conf)

        # ── Path 3: 知识图谱健康 ──
        orphan_ratio = state.get("orphan_ratio")
        components = state.get("connected_components")
        if orphan_ratio is not None and components is not None:
            if (
                isinstance(orphan_ratio, (int, float))
                and isinstance(components, (int, float))
                and float(orphan_ratio) < self._max_orphan_ratio
                and int(components) <= 1
            ):
                self._reason_str = (
                    f"semantic_converged(kg_healthy orphan={float(orphan_ratio):.3f} "
                    f"components={int(components)})"
                )
                return True

        return False

    def reason(self) -> str:
        return self._reason_str or "semantic_not_converged"


class CompletenessGate(HaltingCondition):
    """完整度闸门 — 所有 must 级验证标准通过才停止。

    这是 GovernedCodeAgentLoop 的核心 HaltingCondition：
      - Agent 产出未达标（must 项失败）→ 继续循环
      - Agent 产出达标（must 项全过）→ 停止

    通过 HaltingContext.state["verification_report"] 接收验证报告。
    该 report 由 GovernedCodeAgentLoop._run_governed_cycle() 在每周期放入。
    """

    def __init__(self, independence_decl: Any | None = None) -> None:
        self._last_report: dict[str, Any] | None = None
        self._independence_decl = independence_decl

    def should_halt(self, ctx: HaltingContext) -> bool:
        report = ctx.state.get("verification_report")
        if report is None or not isinstance(report, dict):
            return False
        self._last_report = report
        must_fail = report.get("must_fail", 0)
        if must_fail != 0:
            return False
        # V3：停机裁决改由独立验证器把关——独立性不通过时，即使 must 项
        # 全过也不停机（防止执行器自评通过）。
        if self._independence_decl is not None:
            from maref.verifier.independence import verify_independence

            return verify_independence(self._independence_decl).ok()
        return True

    def reason(self) -> str:
        if self._last_report:
            return (
                f"completeness(must_pass={self._last_report.get('must_pass', 0)},"
                f"must_fail={self._last_report.get('must_fail', 0)})"
            )
        return "completeness(pending)"


class EvalScoreGate(HaltingCondition):
    """评估分数闸门 — 累计评估分数达到阈值才停止。

    从 ctx.state["_evaluations"] 读取跨周期 EvaluationResult，
    检查最近 N 轮的平均分是否 >= min_score，且周期数 >= min_cycles。

    用法:
        gate = EvalScoreGate(min_score=0.85, min_cycles=3)
        loop_config = LoopConfig(halting_condition=AnyOf(gate, ...))
    """

    def __init__(
        self,
        min_score: float = 0.85,
        min_cycles: int = 3,
        window: int = 5,
    ) -> None:
        self._min_score = min_score
        self._min_cycles = min_cycles
        self._window = window
        self._reason_str = "eval_score(pending)"

    def should_halt(self, ctx: HaltingContext) -> bool:
        evals = ctx.state.get("_evaluations", [])
        if not isinstance(evals, list) or len(evals) < self._min_cycles:
            self._reason_str = (
                f"eval_score(waiting {len(evals)}/{self._min_cycles} cycles)"
            )
            return False

        recent = evals[-self._window:]
        try:
            avg_score = sum(e.score for e in recent) / len(recent)
        except (TypeError, AttributeError):
            return False

        if avg_score >= self._min_score:
            self._reason_str = (
                f"eval_score(halt avg={avg_score:.3f} >= {self._min_score})"
            )
            return True

        self._reason_str = (
            f"eval_score(continue avg={avg_score:.3f} < {self._min_score})"
        )
        return False

    def reason(self) -> str:
        return self._reason_str


class HumanConfirmationGate(HaltingCondition):
    """人类确认闸门 — 要求外部人工审批后才能放行/停止。

    三种响应路径:
      - human_approved=True  → halt（人类确认通过，停止循环）
      - human_approved=False → continue（人类拒绝，继续循环）
      - 未设置 + 已触发       → wait（等待确认，不停止也不继续）
      - 超时                 → 按 auto_approve_on_timeout 决策

    human_approved 由外部机制设置（如 convergence_verifier --approve）。
    通过 ctx.state["human_approved"] 接收审批信号。

    用法:
        gate = HumanConfirmationGate(
            trigger_condition="ctx.state.get('must_fail', 0) == 0",
            timeout_seconds=86400,
        )
    """

    def __init__(
        self,
        trigger_condition: str | None = None,
        timeout_seconds: float = 86400.0,
        auto_approve_on_timeout: bool = False,
    ) -> None:
        self._trigger_condition = trigger_condition
        self._timeout = timeout_seconds
        self._auto_approve = auto_approve_on_timeout
        self._triggered_at: float | None = None
        self._reason_str = "human_gate(not_triggered)"

    def should_halt(self, ctx: HaltingContext) -> bool:
        human_approved = ctx.state.get("human_approved", None)

        if human_approved is True:
            self._reason_str = "human_gate(approved)"
            return True

        if human_approved is False:
            self._reason_str = "human_gate(rejected)"
            return False

        # 检查触发条件
        if self._trigger_condition and not self._eval_trigger(ctx):
            self._triggered_at = None
            self._reason_str = f"human_gate(not_triggered: {self._trigger_condition})"
            return False

        # 已触发：记录时间
        if self._triggered_at is None:
            self._triggered_at = time.time()

        elapsed = time.time() - self._triggered_at
        if elapsed >= self._timeout:
            self._reason_str = (
                f"human_gate(timeout approve={self._auto_approve})"
            )
            return self._auto_approve

        self._reason_str = (
            f"human_gate(waiting elapsed={elapsed:.0f}s)"
        )
        return False

    def _eval_trigger(self, ctx: HaltingContext) -> bool:
        try:
            if self._trigger_condition is None:
                return False
            return bool(eval(self._trigger_condition, {"ctx": ctx, "__builtins__": {}}, {}))
        except Exception:
            return False

    def reason(self) -> str:
        return self._reason_str
