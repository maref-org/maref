from __future__ import annotations

import pytest

from maref.governance.types import GovernanceState
from maref.identity.did_registry import AgentDID
from maref.orchestration.joint_machine import JointState, JointStateMachine


class TestJointStateMachine:
    @pytest.fixture
    def jsm(self) -> JointStateMachine:
        return JointStateMachine(max_sync_deviation_ms=10.0)

    def test_initial_state(self, jsm: JointStateMachine) -> None:
        assert jsm.current_state == JointState.IDLE

    def test_register_agent_changes_state(self, jsm: JointStateMachine) -> None:
        jsm.register_agent(AgentDID.generate())
        assert jsm.current_state == JointState.COORDINATING
        assert jsm.agent_count == 1

    def test_sync_agent_updates_slot(self, jsm: JointStateMachine) -> None:
        did = AgentDID.generate()
        jsm.register_agent(did)
        delta_ms = jsm.sync_agent(did, GovernanceState.ACT)
        assert delta_ms >= 0
        slot = jsm.get_slot(did)
        assert slot is not None
        assert slot.maref_state == GovernanceState.ACT

    def test_sync_unknown_agent_raises(self, jsm: JointStateMachine) -> None:
        with pytest.raises(ValueError):
            jsm.sync_agent(AgentDID.generate(), GovernanceState.ACT)

    def test_sync_deviation_low(self, jsm: JointStateMachine) -> None:
        did = AgentDID.generate()
        jsm.register_agent(did)
        delta = jsm.sync_agent(did, GovernanceState.ACT)
        assert delta < 50

    def test_barrier_advance(self, jsm: JointStateMachine) -> None:
        did = AgentDID.generate()
        jsm.register_agent(did)
        v1 = jsm.barrier_clock
        v2 = jsm.advance_barrier()
        assert v1.happens_before(v2)
        slot = jsm.get_slot(did)
        assert slot is not None
        # After advance_barrier, slot.vector_clock merges v2, so it dominates v2
        assert slot.vector_clock.dominates(v2)

    def test_force_halt(self, jsm: JointStateMachine) -> None:
        did = AgentDID.generate()
        jsm.register_agent(did, GovernanceState.ACT)
        jsm.force_halt("Test halt")
        assert jsm.current_state == JointState.HALTED
        slot = jsm.get_slot(did)
        assert slot is not None
        assert slot.maref_state == GovernanceState.HALT

    def test_force_stabilize(self, jsm: JointStateMachine) -> None:
        did = AgentDID.generate()
        jsm.register_agent(did)
        jsm.force_stabilize("Test stabilize")
        assert jsm.current_state == JointState.STABILIZING
        slot = jsm.get_slot(did)
        assert slot is not None
        assert slot.maref_state == GovernanceState.STABILIZE

    def test_get_slot_none(self, jsm: JointStateMachine) -> None:
        assert jsm.get_slot(AgentDID.generate()) is None

    def test_multiple_agents_stabilize(self, jsm: JointStateMachine) -> None:
        dids = [AgentDID.generate() for _ in range(3)]
        for did in dids:
            jsm.register_agent(did)
        assert jsm.agent_count == 3
        jsm.force_stabilize("Multi-agent stabilize")
        for did in dids:
            slot = jsm.get_slot(did)
            assert slot is not None
            assert slot.maref_state == GovernanceState.STABILIZE
