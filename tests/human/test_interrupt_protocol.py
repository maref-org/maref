from __future__ import annotations

import pytest

from maref.human.interrupt_protocol import InterruptProtocol, InterruptSignal, InterruptType


class TestInterruptSignal:
    def test_frozen_dataclass(self) -> None:
        sig = InterruptSignal(
            signal_id="s1",
            interrupt_type=InterruptType.PAUSE,
            target_agents=["agent1"],
            global_sequence=1,
            issued_by="admin",
        )
        assert sig.reason == ""
        assert sig.payload == {}
        assert sig.issued_at > 0

    def test_to_dict(self) -> None:
        sig = InterruptSignal(
            signal_id="s1",
            interrupt_type=InterruptType.ABORT,
            target_agents=[],
            global_sequence=5,
            issued_by="admin",
            reason="emergency",
            payload={"task_id": "t1"},
        )
        d = sig.to_dict()
        assert d["interrupt_type"] == "abort"
        assert d["global_sequence"] == 5
        assert d["reason"] == "emergency"
        assert d["payload"] == {"task_id": "t1"}


class TestInterruptProtocol:
    def test_issue_interrupt_increments_sequence(self) -> None:
        p = InterruptProtocol()
        s1 = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        s2 = p.issue_interrupt(InterruptType.ABORT, issued_by="admin")
        assert s1.global_sequence == 1
        assert s2.global_sequence == 2

    def test_issue_interrupt_with_targets(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(
            InterruptType.OVERRIDE,
            issued_by="admin",
            target_agents=["agent_a", "agent_b"],
            reason="update decision",
            payload={"new_action": "approve"},
        )
        assert sig.target_agents == ["agent_a", "agent_b"]
        assert sig.reason == "update decision"
        assert sig.payload == {"new_action": "approve"}

    def test_issue_interrupt_no_targets(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        assert sig.target_agents == []

    def test_get_latest_interrupt_empty(self) -> None:
        p = InterruptProtocol()
        assert p.get_latest_interrupt() is None

    def test_get_latest_interrupt_after_issue(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        p.issue_interrupt(InterruptType.ABORT, issued_by="admin")
        latest = p.get_latest_interrupt()
        assert latest is not None
        assert latest.interrupt_type == InterruptType.ABORT

    def test_get_interrupt_by_sequence(self) -> None:
        p = InterruptProtocol()
        s1 = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        got = p.get_interrupt(s1.global_sequence)
        assert got is not None
        assert got.signal_id == s1.signal_id

    def test_get_interrupt_not_found(self) -> None:
        p = InterruptProtocol()
        assert p.get_interrupt(999) is None

    def test_get_interrupts_since(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")  # seq=1
        p.issue_interrupt(InterruptType.ABORT, issued_by="admin")  # seq=2
        p.issue_interrupt(InterruptType.RESUME, issued_by="admin")  # seq=3
        since = p.get_interrupts_since(1)
        assert len(since) == 2
        assert since[0].interrupt_type == InterruptType.ABORT
        assert since[1].interrupt_type == InterruptType.RESUME

    def test_get_interrupts_since_none(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        assert p.get_interrupts_since(999) == []

    def test_should_agent_stop_no_interrupts(self) -> None:
        p = InterruptProtocol()
        assert p.should_agent_stop("agent1", 0) is None

    def test_should_agent_stop_already_seen(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        result = p.should_agent_stop("agent1", sig.global_sequence)
        assert result is None

    def test_should_agent_stop_broadcast(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        result = p.should_agent_stop("any_agent", 0)
        assert result is not None
        assert result.interrupt_type == InterruptType.PAUSE

    def test_should_agent_stop_targeted_matches(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(
            InterruptType.ABORT,
            issued_by="admin",
            target_agents=["agent_a"],
        )
        assert p.should_agent_stop("agent_a", 0) is not None
        assert p.should_agent_stop("agent_b", 0) is None

    def test_propagate_to_agents_broadcast(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        delivery = p.propagate_to_agents(["a1", "a2", "a3"], sig)
        assert delivery == {"a1": True, "a2": True, "a3": True}

    def test_propagate_to_agents_targeted(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(
            InterruptType.ABORT,
            issued_by="admin",
            target_agents=["a1"],
        )
        delivery = p.propagate_to_agents(["a1", "a2"], sig)
        assert delivery == {"a1": True, "a2": False}

    def test_propagate_to_agents_no_targets_with_specific_ids(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(InterruptType.RESUME, issued_by="admin")
        delivery = p.propagate_to_agents(["a1", "a2"], sig)
        assert delivery == {"a1": True, "a2": True}

    def test_get_history(self) -> None:
        p = InterruptProtocol()
        p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        p.issue_interrupt(InterruptType.ABORT, issued_by="admin")
        history = p.get_history()
        assert len(history) == 2
        assert history[0].interrupt_type == InterruptType.ABORT  # newest first

    def test_get_history_limit(self) -> None:
        p = InterruptProtocol()
        for i in range(10):
            p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        assert len(p.get_history(limit=3)) == 3

    def test_default_heartbeat_interval(self) -> None:
        p = InterruptProtocol()
        assert p._heartbeat_interval == 1.0

    def test_custom_heartbeat_interval(self) -> None:
        p = InterruptProtocol(heartbeat_interval=0.5)
        assert p._heartbeat_interval == 0.5

    def test_interrupt_immutability(self) -> None:
        p = InterruptProtocol()
        sig = p.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        with pytest.raises((AttributeError, TypeError)):
            sig.reason = "changed"  # type: ignore[misc]
