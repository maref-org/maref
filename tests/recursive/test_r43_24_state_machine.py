from __future__ import annotations

from maref.recursive.agent_24_state_machine import (
    GRAY_CODE_5BIT,
    Agent24StateMachine,
    AgentStateV3,
)


class TestAgentStateV3:
    def test_state_count(self) -> None:
        assert len(list(AgentStateV3)) == 24

    def test_gray_code_coverage(self) -> None:
        for state in AgentStateV3:
            assert state in GRAY_CODE_5BIT, f"Missing Gray code for {state.value}"

    def test_gray_code_5bit(self) -> None:
        codes = list(GRAY_CODE_5BIT.values())
        assert len(set(codes)) == 24, "Gray codes must be unique"


class TestAgent24StateMachine:
    def setup_method(self) -> None:
        self.sm = Agent24StateMachine()

    def test_register(self) -> None:
        self.sm.register("agent_1")
        assert self.sm.state_of("agent_1") == AgentStateV3.UNINITIALIZED

    def test_state_of_nonexistent(self) -> None:
        assert self.sm.state_of("ghost") is None

    def test_gray_code_of(self) -> None:
        self.sm.register("agent_1")
        code = self.sm.gray_code_of("agent_1")
        assert code is not None
        assert len(code) == 5

    def test_valid_transition(self) -> None:
        self.sm.register("agent_1")
        t = self.sm.transition("agent_1", AgentStateV3.BOOTING)
        assert t is not None
        assert t.is_valid
        assert self.sm.state_of("agent_1") == AgentStateV3.BOOTING

    def test_invalid_transition(self) -> None:
        self.sm.register("agent_1")
        t = self.sm.transition("agent_1", AgentStateV3.EXECUTING)
        assert t is not None
        assert not t.is_valid
        assert self.sm.state_of("agent_1") == AgentStateV3.UNINITIALIZED

    def test_force_transition(self) -> None:
        self.sm.register("agent_1")
        t = self.sm.force_transition("agent_1", AgentStateV3.EXECUTING)
        assert t is not None
        assert self.sm.state_of("agent_1") == AgentStateV3.EXECUTING

    def test_check_invariants(self) -> None:
        checks = self.sm.check_invariants()
        assert len(checks) == 5
        assert all(c.holds for c in checks), [
            f"{c.invariant_name}: {c.message}" for c in checks if not c.holds
        ]

    def test_path_exists(self) -> None:
        assert self.sm.path_exists(
            AgentStateV3.UNINITIALIZED, AgentStateV3.TERMINATED
        )

    def test_path_not_exist(self) -> None:
        assert not self.sm.path_exists(
            AgentStateV3.TERMINATED, AgentStateV3.BOOTING
        )

    def test_traversal_path(self) -> None:
        path = self.sm.traversal_path(AgentStateV3.UNINITIALIZED, steps=8)
        assert path is not None
        assert len(path) >= 8

    def test_get_history(self) -> None:
        self.sm.register("agent_1")
        self.sm.transition("agent_1", AgentStateV3.BOOTING)
        self.sm.transition("agent_1", AgentStateV3.REGISTERING)
        history = self.sm.get_history("agent_1")
        assert len(history) >= 2

    def test_agent_count(self) -> None:
        self.sm.register("a1")
        self.sm.register("a2")
        assert self.sm.agent_count == 2

    def test_reset(self) -> None:
        self.sm.register("a1")
        self.sm.reset()
        assert self.sm.agent_count == 0
