from __future__ import annotations

import time

import pytest

from sidecar.adapters.autogen import AutoGenAdapter
from sidecar.protocol import AgentId, AgentState


class _MockChatAgent:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or f"Mock agent {name}"
        self.produced_message_types = []


class _MockGroupChat:
    def __init__(self, participants: list[_MockChatAgent]) -> None:
        self._participants = list(participants)
        self.name = "mock-group-chat"
        self.description = ""


class TestAutoGenAdapterExtended:
    @pytest.fixture
    def agents(self) -> list[_MockChatAgent]:
        return [
            _MockChatAgent("alpha", "Alpha agent"),
            _MockChatAgent("beta", "Beta agent"),
            _MockChatAgent("gamma", "Gamma agent"),
            _MockChatAgent("delta", "Delta agent"),
        ]

    @pytest.fixture
    def adapter(self, agents: list[_MockChatAgent]) -> AutoGenAdapter:
        return AutoGenAdapter(_MockGroupChat(agents))  # type: ignore[arg-type]

    # --- get_state: stale message detection ---

    async def test_get_state_stale_message_stays_running_unless_idled(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha", "old message")
        adapter._last_message_time["alpha"] = time.time() - 60.0
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.RUNNING
        adapter.mark_idle("alpha")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state.state == AgentState.IDLE

    async def test_get_state_recent_message_returns_running(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("beta")
        state = await adapter.get_state(AgentId(name="beta"))
        assert state is not None
        assert state.state == AgentState.RUNNING

    # --- get_state: metadata ---

    async def test_get_state_session_elapsed_increases(
        self, adapter: AutoGenAdapter
    ) -> None:
        state1 = await adapter.get_state(AgentId(name="alpha"))
        assert state1 is not None
        elapsed1 = state1.metadata.get("session_elapsed", 0)
        time.sleep(0.1)
        state2 = await adapter.get_state(AgentId(name="alpha"))
        assert state2 is not None
        elapsed2 = state2.metadata.get("session_elapsed", 0)
        assert elapsed2 >= elapsed1

    async def test_get_state_last_message_seconds_ago_negative_for_no_msg(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="gamma"))
        assert state is not None
        assert state.metadata["last_message_seconds_ago"] == -1.0

    # --- get_state: mark_idle and re-observe cycles ---

    async def test_mark_idle_then_observe_restores_running(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha", "working")
        adapter.mark_idle("alpha")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.IDLE
        adapter.observe_message("alpha", "working again")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.RUNNING

    async def test_mark_idle_multiple_times_no_error(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_idle("alpha")
        adapter.mark_idle("alpha")
        adapter.mark_idle("alpha")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.IDLE

    # --- mark_error scenarios ---

    async def test_mark_error_overrides_previous_state(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.RUNNING
        adapter.mark_error("alpha", "crash")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.ERROR

    async def test_mark_error_then_observe_overrides_error(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_error("beta", "timeout")
        adapter.observe_message("beta", "recovered")
        state = await adapter.get_state(AgentId(name="beta"))
        assert state is not None
        assert state.state == AgentState.RUNNING

    async def test_mark_error_without_task(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_error("gamma")
        state = await adapter.get_state(AgentId(name="gamma"))
        assert state is not None
        assert state.state == AgentState.ERROR
        assert state.current_task == ""

    # --- get_entropy: level thresholds ---

    async def test_get_entropy_warning_level(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter._session_start = time.time() - 1.0
        for _ in range(50):
            adapter.observe_message("alpha")
        entropy = await adapter.get_entropy(AgentId(name="alpha"))
        assert entropy is not None
        assert entropy.value > 0.0

    async def test_get_entropy_contains_all_fields(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha")
        entropy = await adapter.get_entropy(AgentId(name="alpha"))
        assert entropy is not None
        assert hasattr(entropy, "source")
        assert hasattr(entropy, "timestamp")
        assert hasattr(entropy, "value")
        assert hasattr(entropy, "threshold")
        assert hasattr(entropy, "level")

    async def test_get_entropy_level_is_string(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("beta")
        entropy = await adapter.get_entropy(AgentId(name="beta"))
        assert entropy is not None
        assert isinstance(entropy.level, str)

    # --- observe_message: content truncation ---

    async def test_observe_message_truncates_long_content(
        self, adapter: AutoGenAdapter
    ) -> None:
        long_content = "A" * 200
        adapter.observe_message("alpha", long_content)
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert len(state.current_task) <= 120

    async def test_observe_message_empty_content_preserves_previous(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha", "task one")
        adapter.observe_message("alpha", "")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.current_task == "task one"

    # --- reset: repeated ---

    async def test_reset_multiple_times_safe(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha")
        adapter.reset()
        adapter.reset()
        adapter.reset()
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.metadata["total_messages"] == 0

    async def test_reset_clears_explicitly_idle(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_idle("alpha")
        adapter.reset()
        adapter.observe_message("alpha")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.RUNNING

    async def test_reset_preserves_participants(
        self, adapter: AutoGenAdapter
    ) -> None:
        before = await adapter.list_agents()
        adapter.reset()
        after = await adapter.list_agents()
        assert len(before) == len(after)
        assert [a.name for a in before] == [a.name for a in after]

    # --- concurrent agent tracking ---

    async def test_four_agents_independent_tracking(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("alpha", "A1")
        adapter.observe_message("beta", "B1")
        adapter.observe_message("gamma", "G1")
        adapter.observe_message("alpha", "A2")
        adapter.mark_error("delta", "D-err")

        state_a = await adapter.get_state(AgentId(name="alpha"))
        state_b = await adapter.get_state(AgentId(name="beta"))
        state_c = await adapter.get_state(AgentId(name="gamma"))
        state_d = await adapter.get_state(AgentId(name="delta"))

        assert state_a is not None
        assert state_a.metadata["total_messages"] == 2
        assert state_a.state == AgentState.RUNNING

        assert state_b is not None
        assert state_b.metadata["total_messages"] == 1
        assert state_b.state == AgentState.RUNNING

        assert state_c is not None
        assert state_c.metadata["total_messages"] == 1

        assert state_d is not None
        assert state_d.state == AgentState.ERROR

    # --- list_agents namespace ---

    async def test_list_agents_namespace_is_autogen(
        self, adapter: AutoGenAdapter
    ) -> None:
        agent_ids = await adapter.list_agents()
        assert all(a.namespace == "autogen" for a in agent_ids)

    # --- participant_count after operations ---

    async def test_participant_count_unchanged_after_operations(
        self, adapter: AutoGenAdapter
    ) -> None:
        initial = adapter.participant_count
        adapter.observe_message("alpha")
        adapter.mark_idle("beta")
        adapter.mark_error("gamma")
        adapter.reset()
        assert adapter.participant_count == initial

    # --- get_state: task_progress and pending_messages ---

    async def test_get_state_has_task_progress_zero(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.task_progress == 0.0

    async def test_get_state_has_pending_messages_zero(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.pending_messages == 0

    # --- adapter with single agent ---

    async def test_single_agent_works(self) -> None:
        agent = _MockChatAgent("solo", "Single agent")
        adapter = AutoGenAdapter(_MockGroupChat([agent]))  # type: ignore[arg-type]
        agents = await adapter.list_agents()
        assert len(agents) == 1
        assert agents[0].name == "solo"
        assert adapter.participant_count == 1

    # --- adapter with many agents ---

    async def test_many_agents(self) -> None:
        many = [_MockChatAgent(f"agent_{i}") for i in range(20)]
        adapter = AutoGenAdapter(_MockGroupChat(many))  # type: ignore[arg-type]
        agents = await adapter.list_agents()
        assert len(agents) == 20
        assert adapter.participant_count == 20

    # --- get_state after mark_error with no explicit idling ---

    async def test_mark_error_then_get_state_stays_error(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_error("alpha", "fatal")
        state = await adapter.get_state(AgentId(name="alpha"))
        assert state is not None
        assert state.state == AgentState.ERROR
        assert state.current_task == "fatal"

    # --- _find helper ---

    async def test_find_returns_none_for_unknown(
        self, adapter: AutoGenAdapter
    ) -> None:
        assert adapter._find("nonexistent") is None

    async def test_find_returns_agent_for_known(
        self, adapter: AutoGenAdapter
    ) -> None:
        result = adapter._find("alpha")
        assert result is not None
        assert result.name == "alpha"

    # --- session_start property after init ---

    async def test_session_start_is_positive(
        self, adapter: AutoGenAdapter
    ) -> None:
        assert adapter._session_start > 0
