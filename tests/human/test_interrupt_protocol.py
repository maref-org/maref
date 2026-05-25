"""Tests for Interrupt Protocol."""

import pytest

from maref.human.interrupt_protocol import (
    InterruptProtocol,
    InterruptSignal,
    InterruptType,
)


class TestInterruptProtocol:
    def test_issue_interrupt(self):
        protocol = InterruptProtocol()
        signal = protocol.issue_interrupt(
            InterruptType.PAUSE,
            issued_by="admin",
            reason="Emergency",
        )
        assert signal.interrupt_type == InterruptType.PAUSE
        assert signal.issued_by == "admin"
        assert signal.global_sequence == 1

    def test_global_sequence_increments(self):
        protocol = InterruptProtocol()
        s1 = protocol.issue_interrupt(InterruptType.PAUSE, issued_by="a")
        s2 = protocol.issue_interrupt(InterruptType.ABORT, issued_by="b")
        assert s1.global_sequence == 1
        assert s2.global_sequence == 2

    def test_get_latest_interrupt(self):
        protocol = InterruptProtocol()
        assert protocol.get_latest_interrupt() is None

        protocol.issue_interrupt(InterruptType.PAUSE, issued_by="a")
        latest = protocol.get_latest_interrupt()
        assert latest is not None
        assert latest.interrupt_type == InterruptType.PAUSE

    def test_should_agent_stop_broadcast(self):
        protocol = InterruptProtocol()
        protocol.issue_interrupt(InterruptType.ABORT, issued_by="admin")

        # Broadcast (empty target_agents) affects all agents
        signal = protocol.should_agent_stop("agent_1", last_seen_sequence=0)
        assert signal is not None
        assert signal.interrupt_type == InterruptType.ABORT

        # Already seen
        signal = protocol.should_agent_stop("agent_1", last_seen_sequence=1)
        assert signal is None

    def test_should_agent_stop_targeted(self):
        protocol = InterruptProtocol()
        protocol.issue_interrupt(
            InterruptType.PAUSE,
            issued_by="admin",
            target_agents=["agent_1"],
        )

        signal = protocol.should_agent_stop("agent_1", last_seen_sequence=0)
        assert signal is not None

        signal = protocol.should_agent_stop("agent_2", last_seen_sequence=0)
        assert signal is None  # Not targeted

    def test_get_interrupts_since(self):
        protocol = InterruptProtocol()
        protocol.issue_interrupt(InterruptType.PAUSE, issued_by="a")
        protocol.issue_interrupt(InterruptType.ABORT, issued_by="b")
        protocol.issue_interrupt(InterruptType.RESUME, issued_by="c")

        since = protocol.get_interrupts_since(1)
        assert len(since) == 2  # seq 2 and 3
        assert since[0].interrupt_type == InterruptType.ABORT
        assert since[1].interrupt_type == InterruptType.RESUME

    def test_propagate_to_agents(self):
        protocol = InterruptProtocol()
        signal = protocol.issue_interrupt(
            InterruptType.OVERRIDE,
            issued_by="admin",
            target_agents=["agent_1"],
            payload={"new_decision": "reject"},
        )

        delivery = protocol.propagate_to_agents(["agent_1", "agent_2"], signal)
        assert delivery["agent_1"] is True
        assert delivery["agent_2"] is False

    def test_history(self):
        protocol = InterruptProtocol()
        protocol.issue_interrupt(InterruptType.PAUSE, issued_by="a")
        protocol.issue_interrupt(InterruptType.ABORT, issued_by="b")

        history = protocol.get_history()
        assert len(history) == 2
        assert history[0].interrupt_type == InterruptType.ABORT  # Latest first
        assert history[1].interrupt_type == InterruptType.PAUSE

    def test_signal_immutable(self):
        protocol = InterruptProtocol()
        signal = protocol.issue_interrupt(InterruptType.PAUSE, issued_by="a")

        with pytest.raises(AttributeError):
            signal.reason = "modified"  # frozen dataclass
