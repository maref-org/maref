"""
GovernedLoop — 公共 API 版：执行循环 + 治理检测（卡死/停滞/循环）。

这是 MAREF 开源版的 GovernedLoop，不依赖内部 maref_lite/治理层。
核心能力：
- 组合 LoopBase（执行层）+ HaltingCondition（停滞/超时/收敛）
- 集成 StuckDetector（卡死检测，来自 circuit_breaker）
- 支持自定义治理回调（halt 时触发）

用法:
    loop = GovernedLoop(
        halting_conditions=[MaxIterations(100), Timeout(3600)],
        stuck_detector=StuckDetector(),
        on_halt=lambda reason: print(f"HALT: {reason}"),
    )
    await loop.run(agent, task)
"""

from __future__ import annotations
from abc import abstractmethod

import logging
import time
from typing import Any, Callable, Optional

from maref.loop.base import LoopBase, LoopResult, LoopState, LoopStopReason
from maref.loop.halting import HaltingCondition, HaltingContext
from maref.infra.circuit_breaker import StuckDetector

logger = logging.getLogger("maref.loop.governed")


class GovernedLoop(LoopBase):
    """治理感知的执行循环（公共 API 版）。

    特性:
    - 可配置的停机条件（迭代数、超时、目标达成、收敛检测）
    - StuckDetector 集成：检测卡死模式（错误重复、进度停滞、震荡）
    - halt 回调：治理层可注册 on_halt 处理熔断/告警/记录
    """

    def __init__(
        self,
        evaluator: Any | None = None,
        tool_boundary: Any | None = None,
        max_rounds: int = 50,
        halting_conditions: list[HaltingCondition] | None = None,
        stuck_detector: StuckDetector | None = None,
        on_halt: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(evaluator=evaluator, tool_boundary=tool_boundary, max_rounds=max_rounds)

        # 停机条件（策略模式）
        self._halting_conditions = halting_conditions or [
            MaxIterations(max_rounds),
            Timeout(max_rounds * 60.0),  # 默认每轮 60s 预算
        ]

        # 卡死检测器
        self._stuck_detector = stuck_detector or StuckDetector(agent_id="governed_loop")

        # halt 回调（治理层接入点）
        self._on_halt = on_halt

        # 内部状态
        self._halt_reason: str | None = None
        self._start_time: float = 0.0
        self._errors: list[str] = []

    def _check_halt(self, ctx: HaltingContext) -> Optional[str]:
        """检查所有停机条件，返回首个触发的 reason 或 None。"""
        for cond in self._halting_conditions:
            if cond.should_halt(ctx):
                return cond.reason()
        return None

    def _check_stuck(self, ctx: HaltingContext) -> Optional[str]:
        """检查 StuckDetector。"""
        try:
            if self._stuck_detector.check(ctx.state):
                return "stuck_detected"
        except Exception:
            pass
        return None

    async def run(self, *args: Any, **kwargs: Any) -> LoopResult[Any]:
        """运行循环，直到触发停机条件或卡死检测。"""
        self._running = True
        self._start_time = time.time()
        self._state = LoopState()  # 重置状态

        while self._running:
            self._state.round += 1

            # 检查标准停止条件
            stop_reason = self._check_stop()
            if stop_reason:
                return self._finalize(stop_reason)

            # 构建 HaltingContext
            ctx = HaltingContext(
                iteration=self._state.round,
                elapsed_seconds=time.time() - self._start_time,
                state={
                    "round": self._state.round,
                    "consecutive_failures": self._state.consecutive_failures,
                    "last_score": self._state.last_score,
                    "scores": list(self._state.scores),
                },
                errors=len(self._errors),
            )

            # 停机条件检查
            halt_reason = self._check_halt(ctx)
            if halt_reason:
                self._halt_reason = halt_reason
                self._trigger_halt(halt_reason)
                return self._finalize(LoopStopReason.HALT, output={"halt_reason": halt_reason})

            # 卡死检测
            stuck_reason = self._check_stuck(ctx)
            if stuck_reason:
                self._halt_reason = stuck_reason
                self._trigger_halt(stuck_reason)
                return self._finalize(LoopStopReason.STUCK, halt_reason=stuck_reason)

            # 执行子类的单步逻辑（由具体 Agent 实现）
            try:
                await self._run_cycle(*args, **kwargs)
            except Exception as e:
                self._errors.append(str(e))
                self._state.consecutive_failures += 1
                logger.warning("Cycle error: %s", e)
                continue

            self._state.consecutive_failures = 0

        return self._finalize(LoopStopReason.MANUAL)

    def _trigger_halt(self, reason: str) -> None:
        """触发 halt 回调（治理层接入点）。"""
        logger.warning("GovernedLoop HALT: %s", reason)
        if self._on_halt:
            try:
                self._on_halt(reason)
            except Exception as e:
                logger.error("on_halt callback failed: %s", e)

    @abstractmethod
    async def _run_cycle(self, *args: Any, **kwargs: Any) -> None:
        """子类实现：单轮执行逻辑。"""
        ...


# 便捷导出：从 halting 重新导出常用条件
from maref.loop.halting import (
    HaltingCondition,
    HaltingContext,
    MaxIterations,
    Timeout,
    GoalAchieved,
    ConvergenceDetected,
    AnyOf, AllOf,
)

__all__ = [
    "GovernedLoop",
    "StuckDetector",
    "HaltingCondition",
    "HaltingContext",
    "MaxIterations",
    "Timeout",
    "GoalAchieved",
    "ConvergenceDetected",
    "AnyOf, AllOf",
]
