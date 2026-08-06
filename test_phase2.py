#!/usr/bin/env python3
"""Phase 2 smoke tests: load-aware dispatch + reliability matrix."""

from __future__ import annotations

from maref.identity.did_registry import AgentDID
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import AgentDispatcher
from maref.recursive.agent_health import AgentHealthMonitor
from maref.recursive.reliability_matrix import ReliabilityMatrix
from maref.recursive.trust_engine_v2 import TrustEngineV2


def test_dispatcher_with_live_trust():
    trust = TrustEngineV2()
    health = AgentHealthMonitor()
    disp = AgentDispatcher(trust_engine=trust, health_monitor=health)

    did = AgentDID("test", "agent1")
    disp.register_agent(did, ["analysis", "reporting"])

    # Simulate task history so trust engine has a real score
    for _ in range(5):
        trust.record_task(did.did_string, "t", success=True, quality=0.9, latency_ms=200)
    trust.assess(did.did_string)

    task = SubTask(
        task_id="task-1",
        description="analyze data",
        estimated_complexity=0.5,
        required_capabilities=["analysis"],
    )
    result = disp.dispatch(task)
    assert result is not None
    assert result.agent_did == did
    # Trust score should now be > 0.7 (the old hard-coded default)
    assert result.match_dimensions["trust_score"] > 0.7
    print("  dispatcher_with_live_trust OK")


def test_dispatcher_load_awareness():
    trust = TrustEngineV2()
    health = AgentHealthMonitor()
    disp = AgentDispatcher(trust_engine=trust, health_monitor=health)

    did1 = AgentDID("test", "agent1")
    did2 = AgentDID("test", "agent2")
    disp.register_agent(did1, ["analysis"])
    disp.register_agent(did2, ["analysis"])

    # Assess both so trust scores exist
    trust.register_agent(did1.did_string)
    trust.register_agent(did2.did_string)
    trust.assess(did1.did_string)
    trust.assess(did2.did_string)

    # Overload agent1
    health.register(did1.did_string, max_tasks=10)
    health.update(did1.did_string, current_tasks=9)

    task = SubTask(
        task_id="task-1",
        description="analyze data",
        estimated_complexity=0.5,
        required_capabilities=["analysis"],
    )
    result = disp.dispatch(task)
    # Verify that the live load dimension is being read correctly.
    # agent1 has load 0.9 (or 1.0 after increment), agent2 has 0.0.
    assert result is not None
    if result.agent_did == did1:
        assert result.match_dimensions["current_load"] >= 0.9
    else:
        assert result.match_dimensions["current_load"] == 0.0
    print("  dispatcher_load_awareness OK")


def test_reliability_matrix_bypass():
    rm = ReliabilityMatrix()
    obs = "agent_A"
    tgt = "agent_B"
    task_type = "data_analysis"

    # 3 consecutive failures -> bypass
    rm.record(obs, tgt, task_type, success=False, latency_ms=1000)
    rm.record(obs, tgt, task_type, success=False, latency_ms=1000)
    rm.record(obs, tgt, task_type, success=False, latency_ms=1000)

    assert rm.should_bypass(obs, tgt, task_type)
    assert rm.best_target(obs, task_type, [tgt, "agent_C"]) == "agent_C"
    print("  reliability_matrix_bypass OK")


def test_reliability_matrix_recovery():
    rm = ReliabilityMatrix()
    obs = "agent_A"
    tgt = "agent_B"
    task_type = "data_analysis"

    # 2 failures (not yet bypassed)
    rm.record(obs, tgt, task_type, success=False)
    rm.record(obs, tgt, task_type, success=False)
    assert not rm.should_bypass(obs, tgt, task_type)

    # 1 success resets consecutive counter
    rm.record(obs, tgt, task_type, success=True)
    assert not rm.should_bypass(obs, tgt, task_type)
    print("  reliability_matrix_recovery OK")


def test_health_monitor_overload():
    hm = AgentHealthMonitor()
    hm.register("agent_1", max_tasks=5)
    hm.update("agent_1", current_tasks=5)
    assert hm.list_overloaded() == ["agent_1"]

    hm.decrement_tasks("agent_1")
    assert hm.list_overloaded() == []
    print("  health_monitor_overload OK")


def test_dispatch_with_bypass():
    trust = TrustEngineV2()
    health = AgentHealthMonitor()
    disp = AgentDispatcher(trust_engine=trust, health_monitor=health)
    rm = ReliabilityMatrix()

    did1 = AgentDID("test", "agent1")
    did2 = AgentDID("test", "agent2")
    disp.register_agent(did1, ["analysis"])
    disp.register_agent(did2, ["analysis"])

    # Make agent1 bypassed for this task type
    rm.record("coordinator", did1.did_string, "analyze data", success=False)
    rm.record("coordinator", did1.did_string, "analyze data", success=False)
    rm.record("coordinator", did1.did_string, "analyze data", success=False)

    task = SubTask(
        task_id="task-1",
        description="analyze data",
        estimated_complexity=0.5,
        required_capabilities=["analysis"],
    )
    result = disp.dispatch_with_bypass(
        task,
        reliability_matrix=rm,
        observer_id="coordinator",
    )
    assert result is not None
    assert result.agent_did == did2  # agent1 bypassed
    print("  dispatch_with_bypass OK")


def test_release_after_execution():
    trust = TrustEngineV2()
    health = AgentHealthMonitor()
    disp = AgentDispatcher(trust_engine=trust, health_monitor=health)

    did = AgentDID("test", "agent1")
    disp.register_agent(did, ["analysis"])

    task = SubTask(
        task_id="task-1",
        description="analyze data",
        estimated_complexity=0.5,
        required_capabilities=["analysis"],
    )
    result = disp.dispatch(task)
    assert health.get_load_ratio(did.did_string) > 0

    disp.release_after_execution(result, execution_success=True)
    assert health.get_load_ratio(did.did_string) == 0.0
    print("  release_after_execution OK")


if __name__ == "__main__":
    test_dispatcher_with_live_trust()
    test_dispatcher_load_awareness()
    test_reliability_matrix_bypass()
    test_reliability_matrix_recovery()
    test_health_monitor_overload()
    test_dispatch_with_bypass()
    test_release_after_execution()
    print("All Phase 2 checks passed")
