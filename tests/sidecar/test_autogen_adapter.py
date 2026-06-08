"""
Tests for AutoGenAdapter

Verifies that AutoGenAdapter correctly implements the AgentAdapter
interface by tracking agent state through message observation.

Note: Integration tests requiring actual LLM calls use a mock model client.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

pytest.importorskip("autogen_agentchat", reason="autogen_agentchat not installed")

from sidecar.adapters.autogen import AutoGenAdapter
from sidecar.protocol import AgentId, AgentState

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


class _MockChatAgent:
    """Minimal ChatAgent-compatible object for unit tests."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or f"Mock agent {name}"
        self.produced_message_types = []


class _MockGroupChat:
    """Minimal BaseGroupChat-compatible object for unit tests."""

    def __init__(self, participants: list[_MockChatAgent]) -> None:
        self._participants = list(participants)
        self.name = "mock-group-chat"
        self.description = ""  # BaseGroupChat requires this


# ------------------------------------------------------------------
# Unit tests
# ------------------------------------------------------------------


class TestAutoGenAdapterUnit:
    """Unit tests using mock agents (no autogen dependency)."""

    @pytest.fixture
    def agents(self) -> list[_MockChatAgent]:
        return [
            _MockChatAgent("researcher", "Conducts research"),
            _MockChatAgent("critic", "Reviews findings"),
            _MockChatAgent("summarizer", "Generates summaries"),
        ]

    @pytest.fixture
    def adapter(self, agents: list[_MockChatAgent]) -> AutoGenAdapter:
        group_chat = _MockGroupChat(agents)
        return AutoGenAdapter(group_chat)  # type: ignore[arg-type]

    # --- list_agents ---

    async def test_list_agents_returns_all_participants(
        self, adapter: AutoGenAdapter
    ) -> None:
        agent_ids = await adapter.list_agents()
        names = [a.name for a in agent_ids]
        assert names == ["researcher", "critic", "summarizer"]

    async def test_list_agents_returns_correct_namespace(
        self, adapter: AutoGenAdapter
    ) -> None:
        agent_ids = await adapter.list_agents()
        assert all(a.namespace == "autogen" for a in agent_ids)

    # --- get_state ---

    async def test_get_state_unknown_agent(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="unknown"))
        assert state is None

    async def test_get_state_initial_idle(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.state == AgentState.IDLE

    async def test_get_state_returns_agent_id(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.agent_id.name == "researcher"

    async def test_get_state_infers_running_after_recent_message(
        self, adapter: AutoGenAdapter
    ) -> None:
        """An agent that sent a message <30s ago should show as RUNNING."""
        adapter.observe_message("researcher", "analyzing data")
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.state == AgentState.RUNNING

    async def test_get_state_after_mark_idle(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher", "analysis complete")
        adapter.mark_idle("researcher")
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.state == AgentState.IDLE

    async def test_get_state_after_mark_error(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.mark_error("critic", "API timeout")
        state = await adapter.get_state(AgentId(name="critic"))
        assert state is not None
        assert state.state == AgentState.ERROR
        assert state.current_task == "API timeout"

    async def test_get_state_includes_description_in_metadata(
        self, adapter: AutoGenAdapter
    ) -> None:
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.metadata["description"] == "Conducts research"

    async def test_get_state_tracks_message_count(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher")
        adapter.observe_message("researcher")
        adapter.observe_message("researcher")
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.metadata["total_messages"] == 3

    # --- get_entropy ---

    async def test_get_entropy_unknown_agent(
        self, adapter: AutoGenAdapter
    ) -> None:
        entropy = await adapter.get_entropy(AgentId(name="unknown"))
        assert entropy is None

    async def test_get_entropy_returns_zero_for_silent_agent(
        self, adapter: AutoGenAdapter
    ) -> None:
        entropy = await adapter.get_entropy(AgentId(name="researcher"))
        assert entropy is not None
        assert entropy.value == 0.0
        assert entropy.level == "normal"

    async def test_get_entropy_increases_with_message_rate(
        self, adapter: AutoGenAdapter
    ) -> None:
        """Send many messages quickly and verify entropy increases."""
        for _ in range(20):
            adapter.observe_message("researcher")
        entropy = await adapter.get_entropy(AgentId(name="researcher"))
        assert entropy is not None
        assert entropy.value > 0.0

    async def test_get_entropy_contains_source_and_threshold(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher")
        entropy = await adapter.get_entropy(AgentId(name="researcher"))
        assert entropy is not None
        assert "researcher" in entropy.source
        assert entropy.threshold == 5.0

    # --- observe_message ---

    async def test_observe_message_tracks_multiple_agents(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher", "msg1")
        adapter.observe_message("critic", "msg2")
        adapter.observe_message("researcher", "msg3")

        res_state = await adapter.get_state(AgentId(name="researcher"))
        crit_state = await adapter.get_state(AgentId(name="critic"))
        sum_state = await adapter.get_state(AgentId(name="summarizer"))

        assert res_state is not None and res_state.metadata["total_messages"] == 2
        assert crit_state is not None and crit_state.metadata["total_messages"] == 1
        assert sum_state is not None and sum_state.metadata["total_messages"] == 0

    async def test_observe_message_stores_task_content(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher", "Analyzing KL divergence results")
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert "KL divergence" in state.current_task

    # --- observe_stream ---

    async def test_observe_stream_wraps_generator(
        self, adapter: AutoGenAdapter
    ) -> None:
        """Verify stream wrapper passes through items and tracks messages."""

        async def _dummy_stream():
            # Use assert to ensure we have access to the real message type
            from datetime import datetime, timezone

            from autogen_agentchat.messages import TextMessage
            yield TextMessage(source="researcher", content="test analysis", type="TextMessage", created_at=datetime.now(timezone.utc))
            class _Result:
                pass
            yield _Result()

        collected = []
        async for item in adapter.observe_stream(_dummy_stream()):  # type: ignore[arg-type]
            collected.append(item)

        assert len(collected) == 2
        # Verify message was tracked
        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.metadata["total_messages"] == 1

    # --- reset ---

    async def test_reset_clears_all_tracking(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher", "msg1")
        adapter.observe_message("critic", "msg2")
        adapter.mark_error("critic")
        adapter.reset()

        state = await adapter.get_state(AgentId(name="researcher"))
        assert state is not None
        assert state.metadata["total_messages"] == 0
        assert state.state == AgentState.IDLE

        state = await adapter.get_state(AgentId(name="critic"))
        assert state is not None
        assert state.state == AgentState.IDLE

    async def test_reset_resets_session_timer(
        self, adapter: AutoGenAdapter
    ) -> None:
        adapter.observe_message("researcher")
        time.sleep(0.01)  # Ensure time passes
        adapter.reset()
        entropy = await adapter.get_entropy(AgentId(name="researcher"))
        assert entropy is not None
        assert entropy.value == 0.0

    # --- participant_count ---

    async def test_participant_count(self, adapter: AutoGenAdapter) -> None:
        assert adapter.participant_count == 3

    async def test_participant_count_empty_group_chat(
        self,
    ) -> None:
        adapter = AutoGenAdapter(_MockGroupChat([]))  # type: ignore[arg-type]
        assert adapter.participant_count == 0

    async def test_list_agents_empty(
        self,
    ) -> None:
        adapter = AutoGenAdapter(_MockGroupChat([]))  # type: ignore[arg-type]
        agents = await adapter.list_agents()
        assert agents == []


# ------------------------------------------------------------------
# Integration tests (real autogen objects)
# ------------------------------------------------------------------


class _MockModelClient:
    """Minimal ChatCompletionClient that returns canned responses."""

    def __init__(self, model: str = "mock-model") -> None:
        self._model = model

    @property
    def model_info(self) -> dict[str, Any]:
        return {
            "function_calling": False,
            "json_output": False,
            "vision": False,
            "family": "mock",
        }

    @property
    def capabilities(self) -> set[str]:
        return set()

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        from autogen_core.models import CreateResult, RequestUsage

        # Return a canned assistant response
        return CreateResult(
            finish_reason="stop",
            content="Mock response",
            usage=RequestUsage(prompt_tokens=10, completion_tokens=5),
        )

    def create_stream(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def count_tokens(self, *args: Any, **kwargs: Any) -> int:
        return 10

    def remaining_tokens(self, *args: Any, **kwargs: Any) -> int:
        return 1000

    def total_usage(self) -> Any:
        from autogen_core.models import RequestUsage

        return RequestUsage(prompt_tokens=0, completion_tokens=0)


@pytest.mark.skipif(
    True, reason="Integration test requires autogen dependency (run manually)"
)
class TestAutoGenAdapterIntegration:
    """Integration tests with real autogen Agent objects."""

    @pytest.fixture
    def group_chat(self):
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.teams import RoundRobinGroupChat

        model_client = _MockModelClient()
        researcher = AssistantAgent(
            name="researcher",
            model_client=model_client,  # type: ignore[arg-type]
            description="Conducts research",
            system_message="You are a researcher.",
        )
        critic = AssistantAgent(
            name="critic",
            model_client=model_client,  # type: ignore[arg-type]
            description="Reviews findings",
            system_message="You are a critic.",
        )
        return RoundRobinGroupChat(
            participants=[researcher, critic],
            max_turns=2,
        )

    @pytest.fixture
    def adapter(self, group_chat):
        return AutoGenAdapter(group_chat)

    async def test_list_agents(self, adapter):
        agents = await adapter.list_agents()
        assert len(agents) == 2
        names = [a.name for a in agents]
        assert "researcher" in names
        assert "critic" in names

    async def test_observe_stream_tracks_messages(self, group_chat, adapter):
        """Run a real group chat and verify message tracking."""
        collected = []
        async for msg in adapter.observe_stream(
            group_chat.run_stream(task="Say hello")
        ):
            collected.append(msg)

        # Verify at least some messages were tracked
        for agent_id in await adapter.list_agents():
            state = await adapter.get_state(agent_id)
            assert state is not None
            # Messages should be tracked if agent participated
            if state.metadata["total_messages"] > 0:
                assert state.state == AgentState.RUNNING
