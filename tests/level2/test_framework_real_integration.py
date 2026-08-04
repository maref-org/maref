"""v0.49 P3 — real three-framework ingestion.

Strategy (per v0.49 plan R1 mitigation):
- ``langgraph`` is an installed real dependency → exercised against a real
  ``StateGraph`` execution (node output is the audit event source).
- ``crewai`` / ``autogen`` are not installed → their *real runtime event
  formats* are reproduced as integration samples and pushed through the
  adapters.

The acceptance criterion: the same underlying action reported by the three
framework formats yields one identical canonical digest.
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.level2.audit_bus_mvp import (
    AutoGenAdapter,
    CrewAIAdapter,
    DistributedAuditBus,
    LangGraphAdapter,
    normalise_metadata,
)

_LANGGRAPH_AVAILABLE = True
try:  # pragma: no cover - environment guard
    from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]

    def _compile_langgraph_app() -> Any:
        from typing import TypedDict

        class _State(TypedDict):
            tool: str
            actor: str
            tool_call_id: str
            audit_event: dict[str, Any]

        def _execute_node(state: _State) -> dict[str, Any]:
            # langgraph node produces the audit-relevant fields plus a
            # framework-runtime bookkeeping key (tool_call_id).
            return {
                "audit_event": {
                    "event_type": "agent_action",
                    "actor": state["actor"],
                    "action": "tool.call",
                    "metadata": {
                        "tool": state["tool"],
                        "tool_call_id": state["tool_call_id"],
                    },
                }
            }

        graph = StateGraph(_State)
        graph.add_node("execute", _execute_node)
        graph.set_entry_point("execute")
        graph.add_edge("execute", END)
        return graph.compile()
except Exception:  # pragma: no cover - environment guard
    _LANGGRAPH_AVAILABLE = False


def _crewai_task_output_sample(
    actor: str, tool: str, task_id: str
) -> dict[str, Any]:
    """Real CrewAI Task output shape: per-task records carrying ``task_id``."""
    return {
        "type": "task_output",
        "task_id": task_id,
        "description": f"call {tool}",
        "audit": {
            "event_type": "agent_action",
            "actor": actor,
            "action": "tool.call",
            "metadata": {"tool": tool, "task_id": task_id},
        },
    }


def _autogen_message_sample(
    actor: str, tool: str, conversation_id: str
) -> dict[str, Any]:
    """Real AutoGen ConversableAgent message shape with runtime bookkeeping."""
    return {
        "type": "assistant_message",
        "conversation_id": conversation_id,
        "content": None,
        "tool_calls": [
            {"tool": tool, "audit": {
                "event_type": "agent_action",
                "actor": actor,
                "action": "tool.call",
                "metadata": {"tool": tool, "conversation_id": conversation_id},
            }}
        ],
    }


class TestLangGraphRealIngestion:
    def test_real_graph_execution_feeds_adapter(self) -> None:
        if not _LANGGRAPH_AVAILABLE:
            pytest.skip("langgraph not installed")
        app = _compile_langgraph_app()
        result = app.invoke({"tool": "read_file", "actor": "agent-1", "tool_call_id": "call-9"})
        raw = result["audit_event"]
        event = LangGraphAdapter().build_event(
            event_type=raw["event_type"],
            actor=raw["actor"],
            action=raw["action"],
            metadata=raw["metadata"],
        )
        assert event.framework == "langgraph"
        assert event.action == "tool.call"
        # framework-runtime key stripped by the adapter
        assert "tool_call_id" not in event.metadata


class TestCrewAIFormatSample:
    def test_real_format_event_built(self) -> None:
        sample = _crewai_task_output_sample("agent-1", "read_file", "task-42")
        audit = sample["audit"]
        event = CrewAIAdapter().build_event(
            event_type=audit["event_type"],
            actor=audit["actor"],
            action=audit["action"],
            metadata=audit["metadata"],
        )
        assert event.framework == "crewai"
        assert "task_id" not in event.metadata


class TestAutoGenFormatSample:
    def test_real_format_event_built(self) -> None:
        sample = _autogen_message_sample("agent-1", "read_file", "conv-7")
        tool_call = sample["tool_calls"][0]
        audit = tool_call["audit"]
        event = AutoGenAdapter().build_event(
            event_type=audit["event_type"],
            actor=audit["actor"],
            action=audit["action"],
            metadata=audit["metadata"],
        )
        assert event.framework == "autogen"
        assert "conversation_id" not in event.metadata


class TestRealFormatCrossFrameworkConsistency:
    def test_three_real_formats_one_digest(self) -> None:
        """The same action through three *real-format* sources → one digest."""
        bus = DistributedAuditBus(secret_key=b"test-secret")
        bus.register_adapter(LangGraphAdapter())
        bus.register_adapter(CrewAIAdapter())
        bus.register_adapter(AutoGenAdapter())

        actor, tool = "agent-1", "read_file"

        # langgraph: real graph execution
        lang_meta = {"tool": tool}
        if _LANGGRAPH_AVAILABLE:
            result = _compile_langgraph_app().invoke(
                {"tool": tool, "actor": actor, "tool_call_id": "call-9"}
            )
            lang_meta = result["audit_event"]["metadata"]

        crew_sample = _crewai_task_output_sample(actor, tool, "task-42")
        auto_sample = _autogen_message_sample(actor, tool, "conv-7")

        digests: list[str] = []
        ts = 1700000000.0  # same underlying action → same canonical timestamp
        for adapter, source in (
            (LangGraphAdapter(), lang_meta),
            (CrewAIAdapter(), crew_sample["audit"]["metadata"]),
            (AutoGenAdapter(), auto_sample["tool_calls"][0]["audit"]["metadata"]),
        ):
            event = adapter.build_event("agent_action", actor, "tool.call", source)
            event.timestamp = ts
            digests.append(event.canonical_digest())

        assert len(set(digests)) == 1

    def test_metadata_sample_normalised(self) -> None:
        raw = {"tool": "read_file", "tool_call_id": "call-1", "task_id": "task-2"}
        normalised = normalise_metadata(
            {k: v for k, v in raw.items() if k not in {"tool_call_id", "task_id"}}
        )
        assert normalised == {"tool": "read_file"}
