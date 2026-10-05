"""Phase 1.9: StuckDetected 桥接 + GovernedLoop 卡死路径（B3 验收）。

覆盖:
  - StuckDetected 条件：重复模式触发 / 正常路径不触发 / 检测器异常 fail-open
  - add_condition 路径打通（StuckDetector 文档承诺的用法）+ 类型校验
  - 集成：卡死 → loop 以 REPETITION_TRIP 终止并回调 on_halt
  - 对照：无卡死 → 正常跑到 MAX_ROUNDS（正常路径不触发）
"""

from __future__ import annotations

import pytest

from maref.infra.circuit_breaker import StuckDetector
from maref.loop.governed import GovernedLoop
from maref.loop.halting import HaltingContext, MaxIterations, StuckDetected
from maref.loop.protocols import LoopStopReason


def _ctx(iteration: int = 1) -> HaltingContext:
    return HaltingContext(
        iteration=iteration, elapsed_seconds=0.0, state={}, errors=0
    )


def _make_stuck(detector: StuckDetector) -> None:
    """相同 action ×5 → EXACT_REPEAT（DEFAULT_MAX_REPEATS=3）。"""
    for _ in range(5):
        detector.log_action("read_file", {"path": "foo.py"}, "content")


class _ProbeLoop(GovernedLoop):
    """最小可运行子类：计数单轮执行次数。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cycles = 0

    async def _run_cycle(self, *args, **kwargs) -> None:  # noqa: ARG002
        self.cycles += 1


def test_stuck_detected_triggers_on_repeat_pattern():
    detector = StuckDetector(agent_id="t1")
    cond = StuckDetected(detector)
    assert cond.should_halt(_ctx()) is False  # 历史不足 → 不触发
    _make_stuck(detector)
    assert cond.should_halt(_ctx()) is True
    reason = cond.reason()
    assert "stuck_detected" in reason
    assert reason != "stuck_detected(unknown): "  # suggestion 已透传


def test_stuck_detected_normal_path_not_triggers():
    detector = StuckDetector(agent_id="t2")
    for i in range(6):  # 多样化 action → HEALTHY
        detector.log_action(f"tool_{i}", {"i": i}, "ok")
    cond = StuckDetected(detector)
    assert cond.should_halt(_ctx()) is False
    # should_halt 已跑 analyze → report 落在 healthy，不误报
    assert "healthy" in cond.reason() or cond.reason() == ""


def test_stuck_detected_detector_error_fail_open():
    class _Boom:
        def analyze(self) -> dict:
            raise RuntimeError("boom")

    assert StuckDetected(_Boom()).should_halt(_ctx()) is False


def test_add_condition_path打通():
    """StuckDetector 文档承诺的用法：loop.add_condition(StuckDetected(detector))。"""
    detector = StuckDetector(agent_id="t3")
    loop = _ProbeLoop(max_rounds=5)
    loop.add_condition(StuckDetected(detector))
    assert any(isinstance(c, StuckDetected) for c in loop._halting_conditions)
    with pytest.raises(TypeError):
        loop.add_condition("not-a-condition")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_governed_loop_halts_on_stuck():
    """集成：预置卡死模式 → 首轮即终止（早于 _run_cycle），on_halt 回调触发。"""
    detector = StuckDetector(agent_id="t4")
    _make_stuck(detector)
    halted: list[str] = []
    loop = _ProbeLoop(
        max_rounds=10,
        halting_conditions=[MaxIterations(10)],
        stuck_detector=detector,
        on_halt=halted.append,
    )
    res = await loop.run()
    assert res.stop_reason == LoopStopReason.REPETITION_TRIP
    assert "stuck_detected" in str((res.output or {}).get("halt_reason", ""))
    assert halted and "stuck_detected" in halted[0]
    assert loop.cycles == 0  # 卡死检查在 _run_cycle 之前


@pytest.mark.asyncio
async def test_governed_loop_normal_path_runs_to_max_rounds():
    """对照：健康 agent 不被误杀，跑满轮次正常终止。"""
    detector = StuckDetector(agent_id="t5")
    loop = _ProbeLoop(
        max_rounds=4,
        halting_conditions=[MaxIterations(4)],
        stuck_detector=detector,
    )
    res = await loop.run()
    # 语义：round 4 进入时 _check_stop 先触发 MAX_ROUNDS → 实跑 3 轮
    assert res.stop_reason == LoopStopReason.MAX_ROUNDS
    assert loop.cycles == 3
