#!/usr/bin/env python3
"""Phase 1 smoke tests."""

from maref.consensus.nack_protocol import NackBuilder, NackCode, NackHandler, Recoverability
from maref.consensus.vector_clock import VectorClock
from maref.identity.did_registry import AgentDID
from maref.orchestration.joint_machine import JointStateMachine
from maref.orchestration.plan_executor import Plan, PlanExecutor, PlanStep
from maref.orchestration.task_graph import TaskGraph, TaskNode


def test_vector_clock():
    vc1 = VectorClock.new("a")
    vc2 = vc1.tick("a").tick("a")
    assert vc2.clocks["a"] == 2
    assert vc1.happens_before(vc2)
    vc3 = VectorClock.new("b").tick("b")
    assert vc2.is_concurrent_with(vc3)
    print("VectorClock OK")


def test_nack():
    nack = (
        NackBuilder().request("req-1").agents("A", "B").because(NackCode.OVERLOADED, "busy").build()
    )
    assert nack.code == NackCode.OVERLOADED
    handler = NackHandler()
    decision = handler.decide(nack)
    assert decision.recoverability == Recoverability.RETRY
    print("NACK OK")


def test_task_graph_fork_join():
    g = TaskGraph()
    g.add_node(TaskNode("a", "step a"))
    g.add_node(TaskNode("b1", "branch 1"))
    g.add_node(TaskNode("b2", "branch 2"))
    g.add_fork("fork1", ["b1", "b2"])
    g.add_join("join1", ["b1", "b2"])
    assert g.get_fork_branches("fork1") == ["b1", "b2"]
    assert g.get_join_targets("join1") == ["b1", "b2"]
    print("TaskGraph Fork/Join OK")


def test_joint_state_machine():
    jsm = JointStateMachine()
    did = AgentDID("test", "agent1")
    jsm.register_agent(did)
    assert jsm.barrier_clock is not None
    print("JointStateMachine OK")


def test_plan_executor():
    pe = PlanExecutor()
    plan = Plan(
        "p1",
        steps=[
            PlanStep("s1", "echo"),
            PlanStep("s2", "echo", depends_on=["s1"]),
        ],
    )
    report = pe.execute(plan)
    assert report.status.value in ("completed", "partially_completed")
    print("PlanExecutor OK")


if __name__ == "__main__":
    test_vector_clock()
    test_nack()
    test_task_graph_fork_join()
    test_joint_state_machine()
    test_plan_executor()
    print("All Phase 1 checks passed")
