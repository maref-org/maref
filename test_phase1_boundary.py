#!/usr/bin/env python3
"""Phase 1 boundary tests: conflict scenarios, JOIN timeout, NACK recovery chain."""

from __future__ import annotations

import time
from maref.consensus.vector_clock import VectorClock, CausalContext, CausalRelation
from maref.consensus.nack_protocol import (
    NackBuilder, NackCode, NackHandler, Recoverability, RetryPolicy, DEFAULT_RECOVERABILITY,
)
from maref.orchestration.task_graph import TaskGraph, TaskNode, TaskStatus, NodeType
from maref.orchestration.joint_machine import JointStateMachine
from maref.identity.did_registry import AgentDID


# --------------------------------------------------------------------------- #
# VectorClock conflict / edge cases
# --------------------------------------------------------------------------- #
def test_concurrent_conflict_detection():
    """Two agents modify state independently → clocks are concurrent."""
    a = CausalContext("agent_a")
    b = CausalContext("agent_b")

    a.event()          # a=1
    b.event()          # b=1

    assert a.clock.is_concurrent_with(b.clock)
    assert a.clock.compare(b.clock) == CausalRelation.CONCURRENT
    print("  concurrent_conflict OK")


def test_merge_resolves_concurrency():
    """After merge, both histories are visible and causality is restored."""
    a = CausalContext("agent_a")
    b = CausalContext("agent_b")

    a.event()          # a=1
    b.event()          # b=1

    # b receives a's clock
    b.receive(a.clock)  # b merges a, ticks b → a=1,b=2
    # a receives b's updated clock (now a knows b has seen a's event)
    a.receive(b.clock)  # a merges b, ticks a → a=2,b=2

    # After symmetric exchange a dominates b (a has strictly greater or equal
    # in every dimension).  b does NOT dominate a because agent_a=1 < 2.
    assert a.clock.dominates(b.clock)
    assert not b.clock.dominates(a.clock)
    # Causally a happens-after b because a's clock is >= in all dims and > in at least one
    assert a.clock.compare(b.clock) == CausalRelation.AFTER
    print("  merge_resolves_concurrency OK")


def test_dominates_partial_order():
    """dominates() checks vector-wise >= without requiring strict happens-before."""
    vc1 = VectorClock({"a": 3, "b": 2})
    vc2 = VectorClock({"a": 2, "b": 1})
    assert vc1.dominates(vc2)
    assert not vc2.dominates(vc1)
    print("  dominates_partial_order OK")


def test_empty_clock_behavior():
    """Empty clocks should compare equal and dominate each other."""
    empty = VectorClock()
    assert empty.compare(VectorClock()) == CausalRelation.EQUAL
    assert empty.dominates(VectorClock())
    print("  empty_clock_behavior OK")


# --------------------------------------------------------------------------- #
# TaskGraph JOIN timeout / partial completion
# --------------------------------------------------------------------------- #
def test_join_with_failed_branch():
    """JOIN should become ready when all targets are terminal (including FAILED)."""
    g = TaskGraph()
    g.add_node(TaskNode("b1", "branch 1"))
    g.add_node(TaskNode("b2", "branch 2"))
    g.add_join("join1", ["b1", "b2"])

    g.set_node_status("b1", TaskStatus.COMPLETED)
    g.set_node_status("b2", TaskStatus.FAILED)

    ready = g.get_ready_joins()
    assert "join1" in ready, f"Expected join1 in ready joins, got {ready}"
    print("  join_with_failed_branch OK")


def test_join_with_skipped_branch():
    """JOIN should treat SKIPPED as terminal."""
    g = TaskGraph()
    g.add_node(TaskNode("b1", "branch 1"))
    g.add_node(TaskNode("b2", "branch 2"))
    g.add_join("join1", ["b1", "b2"])

    g.set_node_status("b1", TaskStatus.COMPLETED)
    g.set_node_status("b2", TaskStatus.SKIPPED)

    ready = g.get_ready_joins()
    assert "join1" in ready
    print("  join_with_skipped_branch OK")


def test_join_not_ready_when_pending():
    """JOIN must NOT be ready if any target is still PENDING."""
    g = TaskGraph()
    g.add_node(TaskNode("b1", "branch 1"))
    g.add_node(TaskNode("b2", "branch 2"))
    g.add_join("join1", ["b1", "b2"])

    g.set_node_status("b1", TaskStatus.COMPLETED)
    # b2 stays PENDING

    ready = g.get_ready_joins()
    assert "join1" not in ready
    print("  join_not_ready_when_pending OK")


def test_fork_dependency_auto_injection():
    """add_fork should automatically inject fork_id into branch dependencies."""
    g = TaskGraph()
    g.add_node(TaskNode("b1", "branch 1"))
    g.add_node(TaskNode("b2", "branch 2"))
    g.add_fork("fork1", ["b1", "b2"])

    assert "fork1" in g.get_dependencies("b1")
    assert "fork1" in g.get_dependencies("b2")
    print("  fork_dependency_auto_injection OK")


# --------------------------------------------------------------------------- #
# NACK protocol recovery chain
# --------------------------------------------------------------------------- #
def test_nack_default_recoverability_coverage():
    """Every NackCode must have a default recoverability mapping."""
    for code in NackCode:
        assert code in DEFAULT_RECOVERABILITY, f"{code} missing in DEFAULT_RECOVERABILITY"
    print("  nack_default_recoverability_coverage OK")


def test_nack_handler_custom_override():
    """Custom recoverability should override the default."""
    handler = NackHandler()
    handler.set_recoverability(NackCode.OVERLOADED, Recoverability.REROUTE)

    nack = NackBuilder().request("r1").agents("A", "B").because(NackCode.OVERLOADED, "busy").build()
    decision = handler.decide(nack)
    assert decision.recoverability == Recoverability.REROUTE
    print("  nack_handler_custom_override OK")


def test_nack_retry_policy_exponential_backoff():
    """RetryPolicy should produce exponential delays."""
    policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0, backoff_multiplier=2.0)
    assert policy.delay_for_attempt(0) == 1.0
    assert policy.delay_for_attempt(1) == 2.0
    assert policy.delay_for_attempt(2) == 4.0
    assert policy.delay_for_attempt(10) == 60.0  # capped by max_delay_seconds
    print("  nack_retry_policy_exponential_backoff OK")


def test_nack_serialization_roundtrip():
    """NackMessage must survive to_dict -> from_dict roundtrip."""
    original = (
        NackBuilder()
        .request("req-42")
        .agents("agent_X", "agent_Y")
        .because(NackCode.CAPABILITY_MISMATCH, "missing skill")
        .retry_after(5.0)
        .alternatives(["agent_Z", "agent_W"])
        .context({"task_type": "analysis"})
        .build()
    )
    data = original.to_dict()
    restored = type(original).from_dict(data)
    assert restored.code == original.code
    assert restored.recoverability == original.recoverability
    assert restored.suggested_alternative_agents == ["agent_Z", "agent_W"]
    assert restored.retry_after_seconds == 5.0
    print("  nack_serialization_roundtrip OK")


def test_nack_recovery_chain_simulation():
    """Simulate a full recovery chain: OVERLOADED -> RETRY -> REROUTE -> ABORT."""
    handler = NackHandler()
    handler.register_retry_policy(NackCode.OVERLOADED, RetryPolicy(max_retries=1, base_delay_seconds=0.1))

    # 1st attempt: overloaded -> retry
    nack1 = NackBuilder().request("r1").agents("A", "B").because(NackCode.OVERLOADED, "busy").build()
    dec1 = handler.decide(nack1)
    assert dec1.recoverability == Recoverability.RETRY
    assert dec1.retry_policy is not None

    # 2nd attempt: still overloaded after retry -> reroute
    handler.set_recoverability(NackCode.OVERLOADED, Recoverability.REROUTE)
    nack2 = NackBuilder().request("r1").agents("A", "B").because(NackCode.OVERLOADED, "still busy").build()
    dec2 = handler.decide(nack2)
    assert dec2.recoverability == Recoverability.REROUTE

    # 3rd attempt: no alternatives -> abort
    nack3 = NackBuilder().request("r1").agents("A", "C").because(NackCode.SAFETY_GATE_BLOCKED, "denied").build()
    dec3 = handler.decide(nack3)
    assert dec3.recoverability == Recoverability.ABORT
    print("  nack_recovery_chain_simulation OK")


# --------------------------------------------------------------------------- #
# JointStateMachine causal consistency under stress
# --------------------------------------------------------------------------- #
def test_joint_barrier_monotonic():
    """Barrier clock must never decrease."""
    jsm = JointStateMachine()
    did1 = AgentDID("test", "a1")
    did2 = AgentDID("test", "a2")

    jsm.register_agent(did1)
    jsm.register_agent(did2)

    b1 = jsm.barrier_clock.to_dict()
    jsm.sync_agent(did1, jsm.get_slot(did1).maref_state)
    b2 = jsm.barrier_clock.to_dict()

    for k, v in b1.items():
        assert b2.get(k, 0) >= v, f"Barrier clock decreased for {k}: {v} -> {b2.get(k, 0)}"
    print("  joint_barrier_monotonic OK")


def test_joint_causal_summary_serializable():
    """causal_summary() must return a JSON-friendly dict."""
    jsm = JointStateMachine()
    did = AgentDID("test", "a1")
    jsm.register_agent(did)
    summary = jsm.causal_summary()
    assert "state" in summary
    assert "barrier_clock" in summary
    assert "agents" in summary
    assert isinstance(summary["barrier_clock"], dict)
    print("  joint_causal_summary_serializable OK")


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def run_all():
    print("=== VectorClock boundary ===")
    test_concurrent_conflict_detection()
    test_merge_resolves_concurrency()
    test_dominates_partial_order()
    test_empty_clock_behavior()

    print("=== TaskGraph boundary ===")
    test_join_with_failed_branch()
    test_join_with_skipped_branch()
    test_join_not_ready_when_pending()
    test_fork_dependency_auto_injection()

    print("=== NACK boundary ===")
    test_nack_default_recoverability_coverage()
    test_nack_handler_custom_override()
    test_nack_retry_policy_exponential_backoff()
    test_nack_serialization_roundtrip()
    test_nack_recovery_chain_simulation()

    print("=== JointStateMachine boundary ===")
    test_joint_barrier_monotonic()
    test_joint_causal_summary_serializable()

    print("\nAll Phase 1 boundary tests passed")


if __name__ == "__main__":
    run_all()
