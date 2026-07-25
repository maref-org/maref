"""consensus 子系统单元测试。

覆盖三个核心模块：
- vector_clock.py: 向量时钟与因果上下文
- nack_protocol.py: 结构化 NACK 协议
- consistency_dsl.py: 一致性级别 DSL 与动态降级
"""
from __future__ import annotations

from maref.consensus.consistency_dsl import (
    ConsistencyLevel,
    CostEstimator,
    DynamicDegrader,
)
from maref.consensus.nack_protocol import (
    DEFAULT_RECOVERABILITY,
    NackBuilder,
    NackCode,
    NackHandler,
    NackMessage,
    Recoverability,
    RetryPolicy,
)
from maref.consensus.vector_clock import CausalContext, CausalRelation, VectorClock

# ---------------------------------------------------------------------------
# VectorClock
# ---------------------------------------------------------------------------

class TestVectorClock:

    def test_new_creates_single_agent_at_zero(self) -> None:
        """new() 应创建初始时钟，agent_id 对应位置为 0。"""
        vc = VectorClock.new("agent-A")
        assert vc.clocks == {"agent-A": 0}

    def test_tick_increments_and_returns_new_instance(self) -> None:
        """tick() 应递增对应 agent 的计数并返回新实例（不可变性）。"""
        vc = VectorClock.new("agent-A")
        vc2 = vc.tick("agent-A")
        assert vc2.clocks == {"agent-A": 1}
        assert vc.clocks == {"agent-A": 0}  # 原对象不变

    def test_tick_for_new_agent(self) -> None:
        """tick() 一个未出现的 agent_id 应从 1 开始。"""
        vc = VectorClock.new("agent-A")
        vc2 = vc.tick("agent-B")
        assert vc2.clocks == {"agent-A": 0, "agent-B": 1}

    def test_merge_takes_element_wise_max(self) -> None:
        """merge() 应对每个 agent 取最大值。"""
        vc1 = VectorClock({"A": 3, "B": 1})
        vc2 = VectorClock({"A": 1, "B": 5, "C": 2})
        merged = vc1.merge(vc2)
        assert merged.clocks == {"A": 3, "B": 5, "C": 2}

    def test_compare_before(self) -> None:
        """所有维度 self <= other 且至少一个 <，应为 BEFORE。"""
        vc1 = VectorClock({"A": 1, "B": 2})
        vc2 = VectorClock({"A": 3, "B": 2})
        assert vc1.compare(vc2) == CausalRelation.BEFORE

    def test_compare_after(self) -> None:
        """所有维度 self >= other 且至少一个 >，应为 AFTER。"""
        vc1 = VectorClock({"A": 5, "B": 2})
        vc2 = VectorClock({"A": 3, "B": 2})
        assert vc1.compare(vc2) == CausalRelation.AFTER

    def test_compare_equal(self) -> None:
        """所有维度相等应为 EQUAL。"""
        vc1 = VectorClock({"A": 1, "B": 2})
        vc2 = VectorClock({"A": 1, "B": 2})
        assert vc1.compare(vc2) == CausalRelation.EQUAL

    def test_compare_concurrent(self) -> None:
        """一个维度大一个维度小应为 CONCURRENT。"""
        vc1 = VectorClock({"A": 5, "B": 1})
        vc2 = VectorClock({"A": 1, "B": 5})
        assert vc1.compare(vc2) == CausalRelation.CONCURRENT

    def test_happens_before(self) -> None:
        """happens_before 在严格先于时返回 True。"""
        vc1 = VectorClock({"A": 1})
        vc2 = VectorClock({"A": 2})
        assert vc1.happens_before(vc2) is True
        assert vc2.happens_before(vc1) is False

    def test_is_concurrent_with(self) -> None:
        """is_concurrent_with 在不可比较时返回 True。"""
        vc1 = VectorClock({"A": 5, "B": 1})
        vc2 = VectorClock({"A": 1, "B": 5})
        assert vc1.is_concurrent_with(vc2) is True

    def test_dominates(self) -> None:
        """dominates 在所有维度 >= 时返回 True。"""
        vc1 = VectorClock({"A": 3, "B": 5})
        vc2 = VectorClock({"A": 2, "B": 5})
        assert vc1.dominates(vc2) is True
        assert vc2.dominates(vc1) is False

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict 往返应保持数据一致。"""
        original = VectorClock({"A": 3, "B": 7, "C": 1})
        restored = VectorClock.from_dict(original.to_dict())
        assert restored.clocks == original.clocks

    def test_immutability_original_not_mutated(self) -> None:
        """多次 tick/merge 不应改变原对象。"""
        vc = VectorClock.new("A")
        vc.tick("A")
        vc.merge(VectorClock({"B": 5}))
        assert vc.clocks == {"A": 0}


# ---------------------------------------------------------------------------
# CausalContext
# ---------------------------------------------------------------------------

class TestCausalContext:

    def test_event_increments_clock(self) -> None:
        """event() 应递增 agent 自己的时钟。"""
        ctx = CausalContext("agent-A")
        clock = ctx.event()
        assert clock.clocks["agent-A"] == 1

    def test_receive_merges_and_ticks(self) -> None:
        """receive() 应先 merge 再 tick。"""
        ctx = CausalContext("A")
        ctx.event()  # A=1
        sender = VectorClock({"A": 0, "B": 3})
        clock = ctx.receive(sender)
        assert clock.clocks["B"] == 3
        assert clock.clocks["A"] == 2  # merge(0) + tick

    def test_send_ticks_before_returning(self) -> None:
        """send() 应先 tick 再返回时钟。"""
        ctx = CausalContext("A")
        clock = ctx.send()
        assert clock.clocks["A"] == 1

    def test_snapshot_returns_copy(self) -> None:
        """snapshot() 返回的时钟不受后续操作影响。"""
        ctx = CausalContext("A")
        snap = ctx.snapshot()
        ctx.event()
        ctx.event()
        assert snap.clocks == {"A": 0}

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict 往返应保持一致。"""
        ctx = CausalContext("A")
        ctx.event()
        ctx.receive(VectorClock({"B": 5}))
        data = ctx.to_dict()
        restored = CausalContext.from_dict(data)
        assert restored.agent_id == "A"
        assert restored.clock.clocks == ctx.clock.clocks


# ---------------------------------------------------------------------------
# NackProtocol
# ---------------------------------------------------------------------------

class TestNackMessage:

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        """NackMessage 序列化/反序列化应保持一致。"""
        msg = NackMessage(
            nack_id="nack_001",
            request_id="req_001",
            from_agent="A",
            to_agent="B",
            code=NackCode.OVERLOADED,
            reason="too many requests",
            recoverability=Recoverability.RETRY,
            retry_after_seconds=5.0,
            suggested_alternative_agents=["C", "D"],
            context_snapshot={"queue_size": 100},
        )
        data = msg.to_dict()
        restored = NackMessage.from_dict(data)
        assert restored.nack_id == msg.nack_id
        assert restored.code == msg.code
        assert restored.recoverability == msg.recoverability
        assert restored.suggested_alternative_agents == ["C", "D"]

    def test_from_dict_defaults(self) -> None:
        """from_dict 对缺失字段应使用合理默认值。"""
        data = {"nack_id": "n1", "request_id": "r1", "from_agent": "A", "to_agent": "B"}
        msg = NackMessage.from_dict(data)
        assert msg.code == NackCode.UNSPECIFIED
        assert msg.recoverability == Recoverability.ABORT


class TestNackBuilder:

    def test_build_complete_message(self) -> None:
        """Builder 链式调用应产出完整 NackMessage。"""
        msg = (
            NackBuilder()
            .request("req-100")
            .agents("agent-A", "agent-B")
            .because(NackCode.TRUST_TOO_LOW, "trust score below threshold")
            .retry_after(10.0)
            .alternatives(["agent-C"])
            .context({"trust_score": 15})
            .build()
        )
        assert msg.request_id == "req-100"
        assert msg.from_agent == "agent-A"
        assert msg.to_agent == "agent-B"
        assert msg.code == NackCode.TRUST_TOO_LOW
        assert msg.recoverability == Recoverability.REROUTE
        assert msg.retry_after_seconds == 10.0
        assert msg.suggested_alternative_agents == ["agent-C"]

    def test_build_generates_unique_nack_id(self) -> None:
        """每次 build 应生成不同的 nack_id。"""
        b = NackBuilder().request("r").agents("A", "B").because(NackCode.UNSPECIFIED, "")
        m1 = b.build()
        m2 = b.build()
        assert m1.nack_id != m2.nack_id

    def test_build_default_recoverability_for_unspecified(self) -> None:
        """UNSPECIFIED code 默认映射到 ABORT。"""
        msg = NackBuilder().because(NackCode.UNSPECIFIED, "").build()
        assert msg.recoverability == Recoverability.ABORT


class TestNackHandler:

    def test_decide_returns_default_recoverability(self) -> None:
        """未自定义时返回默认 recoverability。"""
        handler = NackHandler()
        nack = NackBuilder().request("r").agents("A", "B").because(NackCode.OVERLOADED, "").build()
        decision = handler.decide(nack)
        assert decision.recoverability == Recoverability.RETRY

    def test_custom_recoverability_overrides_default(self) -> None:
        """set_recoverability 应覆盖默认映射。"""
        handler = NackHandler()
        handler.set_recoverability(NackCode.OVERLOADED, Recoverability.ABORT)
        nack = NackBuilder().request("r").agents("A", "B").because(NackCode.OVERLOADED, "").build()
        decision = handler.decide(nack)
        assert decision.recoverability == Recoverability.ABORT

    def test_decide_with_retry_policy(self) -> None:
        """注册 RetryPolicy 后 decision 应包含它。"""
        handler = NackHandler()
        policy = RetryPolicy(max_retries=5, base_delay_seconds=2.0)
        handler.register_retry_policy(NackCode.OVERLOADED, policy)
        nack = NackBuilder().request("r").agents("A", "B").because(NackCode.OVERLOADED, "").build()
        decision = handler.decide(nack)
        assert decision.retry_policy is not None
        assert decision.retry_policy.max_retries == 5


class TestRetryPolicy:

    def test_delay_for_attempt_exponential_backoff(self) -> None:
        """delay_for_attempt 应按指数退避计算。"""
        policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0, backoff_multiplier=2.0)
        assert policy.delay_for_attempt(0) == 1.0
        assert policy.delay_for_attempt(1) == 2.0
        assert policy.delay_for_attempt(2) == 4.0

    def test_delay_capped_at_max(self) -> None:
        """退避延迟不应超过 max_delay_seconds。"""
        policy = RetryPolicy(base_delay_seconds=1.0, backoff_multiplier=10.0, max_delay_seconds=30.0)
        assert policy.delay_for_attempt(10) == 30.0


class TestDefaultRecoverability:

    def test_safety_gate_blocked_maps_to_abort(self) -> None:
        """SAFETY_GATE_BLOCKED 应映射到 ABORT。"""
        assert DEFAULT_RECOVERABILITY[NackCode.SAFETY_GATE_BLOCKED] == Recoverability.ABORT

    def test_human_in_loop_maps_to_escalate(self) -> None:
        """HUMAN_IN_THE_LOOP_REQUIRED 应映射到 ESCALATE。"""
        assert DEFAULT_RECOVERABILITY[NackCode.HUMAN_IN_THE_LOOP_REQUIRED] == Recoverability.ESCALATE

    def test_all_codes_have_mapping(self) -> None:
        """每个 NackCode 都应有默认映射。"""
        for code in NackCode:
            assert code in DEFAULT_RECOVERABILITY


# ---------------------------------------------------------------------------
# ConsistencyDSL
# ---------------------------------------------------------------------------

class TestCostEstimator:

    def test_estimate_strict_has_highest_latency(self) -> None:
        """STRICT 应有最高延迟。"""
        strict = CostEstimator.estimate(ConsistencyLevel.STRICT)
        causal = CostEstimator.estimate(ConsistencyLevel.CAUSAL)
        eventual = CostEstimator.estimate(ConsistencyLevel.EVENTUAL)
        assert strict.latency_ms > causal.latency_ms > eventual.latency_ms

    def test_compare_returns_delta(self) -> None:
        """compare() 应返回延迟差和通信比率。"""
        result = CostEstimator.compare(ConsistencyLevel.EVENTUAL, ConsistencyLevel.STRICT)
        assert result["latency_delta_ms"] > 0
        assert result["comm_ratio"] > 1.0

    def test_estimate_returns_correct_level(self) -> None:
        """estimate() 返回的 cost 应包含正确的 level。"""
        for level in ConsistencyLevel:
            cost = CostEstimator.estimate(level)
            assert cost.level == level


class TestDynamicDegrader:

    def test_critical_path_not_degraded(self) -> None:
        """critical 路径在高负载下也不降级。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.STRICT, current_load=0.95, is_critical=True)
        assert result == ConsistencyLevel.STRICT

    def test_low_load_no_degradation(self) -> None:
        """低负载下不降级。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.STRICT, current_load=0.5)
        assert result == ConsistencyLevel.STRICT

    def test_high_load_degrades_strict_to_causal(self) -> None:
        """高负载下 STRICT 降级为 CAUSAL。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.STRICT, current_load=0.9)
        assert result == ConsistencyLevel.CAUSAL

    def test_high_load_degrades_causal_to_eventual(self) -> None:
        """高负载下 CAUSAL 降级为 EVENTUAL。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.CAUSAL, current_load=0.9)
        assert result == ConsistencyLevel.EVENTUAL

    def test_high_load_eventual_stays_eventual(self) -> None:
        """高负载下 EVENTUAL 保持不变。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.EVENTUAL, current_load=0.9)
        assert result == ConsistencyLevel.EVENTUAL

    def test_explain_returns_full_dict(self) -> None:
        """explain() 应返回包含所有关键字段的 dict。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.explain("step-1", ConsistencyLevel.STRICT, current_load=0.9)
        assert result["step_id"] == "step-1"
        assert result["requested"] == "strict"
        assert result["effective"] == "causal"
        assert result["is_critical"] is False
        assert "latency_before_ms" in result
        assert "latency_after_ms" in result
        assert "degraded" in result["reason"]

    def test_threshold_boundary_no_degradation(self) -> None:
        """负载恰好等于阈值时应降级（>= 判断）。"""
        degrader = DynamicDegrader(high_load_threshold=0.8)
        result = degrader.resolve("step-1", ConsistencyLevel.STRICT, current_load=0.8)
        assert result == ConsistencyLevel.CAUSAL

    def test_custom_critical_path_level(self) -> None:
        """critical_path_levels 中注册的 step 应使用自定义级别。"""
        degrader = DynamicDegrader(
            high_load_threshold=0.8,
            critical_path_levels={"step-special": ConsistencyLevel.EVENTUAL},
        )
        result = degrader.resolve("step-special", ConsistencyLevel.STRICT, current_load=0.95, is_critical=True)
        assert result == ConsistencyLevel.EVENTUAL
