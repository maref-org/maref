from __future__ import annotations

from maref.loop.protocols import (
    AgentResponse,
    ConversationSummary,
    Discovery,
    EvaluationResult,
    ExplorationResult,
    LoopStopReason,
    ToolBoundary,
    ToolPermission,
    TurnResult,
)


class TestLoopStopReason:
    def test_enum_values(self):
        assert LoopStopReason.MAX_ROUNDS.value == "max_rounds"
        assert LoopStopReason.CONVERGED.value == "converged"
        assert LoopStopReason.MANUAL_STOP.value == "manual_stop"
        assert LoopStopReason.UNKNOWN.value == "unknown"

    def test_enum_members_count(self):
        assert len(LoopStopReason) == 12


class TestToolPermission:
    def test_enum_values(self):
        assert ToolPermission.READ.value == "read"
        assert ToolPermission.WRITE.value == "write"
        assert ToolPermission.DENY.value == "deny"


class TestToolBoundary:
    def test_default_construction(self):
        tb = ToolBoundary()
        assert tb.allowed_domains == []
        assert tb.permissions == {}

    def test_to_dict(self):
        tb = ToolBoundary(
            allowed_domains=["fs", "net"],
            permissions={"fs": ToolPermission.READ, "net": ToolPermission.WRITE},
        )
        d = tb.to_dict()
        assert d["allowed_domains"] == ["fs", "net"]
        assert d["permissions"] == {"fs": "read", "net": "write"}

    def test_code_generation(self):
        tb = ToolBoundary.code_generation()
        assert "filesystem" in tb.allowed_domains
        assert tb.permissions["filesystem"] == ToolPermission.WRITE

    def test_read_only(self):
        tb = ToolBoundary.read_only()
        assert "search" in tb.allowed_domains
        assert tb.permissions["search"] == ToolPermission.READ

    def test_customer_service(self):
        tb = ToolBoundary.customer_service()
        assert "ticketing" in tb.allowed_domains
        assert tb.permissions["crm"] == ToolPermission.WRITE


class TestEvaluationResult:
    def test_defaults(self):
        r = EvaluationResult()
        assert r.score == 0.0
        assert r.errors == []
        assert r.improvement == 0.0

    def test_construction(self):
        r = EvaluationResult(score=0.95, errors=["minor"], improvement=0.1)
        assert r.score == 0.95
        assert r.errors == ["minor"]


class TestDiscovery:
    def test_construction(self):
        d = Discovery(content="found", source_round=1, novelty=0.8, tags=["a", "b"])
        assert d.content == "found"
        assert d.source_round == 1
        assert d.novelty == 0.8


class TestExplorationResult:
    def test_defaults(self):
        r = ExplorationResult()
        assert r.discoveries == []
        assert r.coverage == 0.0

    def test_with_discoveries(self):
        d = Discovery(content="x", tags=["t1"])
        r = ExplorationResult(discoveries=[d], coverage=0.5)
        assert len(r.discoveries) == 1
        assert r.coverage == 0.5


class TestTurnResult:
    def test_construction(self):
        t = TurnResult(
            turn_id=1, user_input="hello", agent_response="hi",
            sentiment_score=0.5, response_time_ms=100,
        )
        assert t.turn_id == 1
        assert t.sentiment_score == 0.5


class TestConversationSummary:
    def test_defaults(self):
        s = ConversationSummary()
        assert s.total_turns == 0
        assert s.resolved is False

    def test_with_turns(self):
        t = TurnResult(turn_id=0)
        s = ConversationSummary(turns=[t], total_turns=1, resolved=True)
        assert s.total_turns == 1
        assert s.resolved is True


class TestAgentResponse:
    def test_defaults(self):
        r = AgentResponse()
        assert r.content == ""
        assert r.end_conversation is False
        assert r.escalate is False

    def test_construction(self):
        r = AgentResponse(content="done", end_conversation=True, escalate=True)
        assert r.content == "done"
        assert r.end_conversation is True
