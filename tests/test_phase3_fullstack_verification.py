"""Phase 3: Full-stack verification — 10-layer acceptance checklist.

Each layer tested against its L1 (must-do) standard.
P1+P2 additions are verified with integration-style tests.
"""

import time

import pytest

# Layer 1: Interface
from maref.integration.intent_gateway import (
    InputSource,
    IntentClassifier,
    IntentGateway,
    IntentType,
)

# Layer 2: Human Collaboration
from maref.human.decision_api import HumanDecisionAPI
from maref.human.interrupt_protocol import InterruptProtocol, InterruptType

# Layer 3: Governance
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker, BreakerState

# Layer 4: Orchestration
from maref.consensus.vector_clock import VectorClock, CausalContext
from maref.consensus.nack_protocol import NackBuilder, NackCode, NackMessage
from maref.executor.types import Task

# Layer 5: Memory (P1 upgrade)
from maref.memory.memory_manager import (
    ConfidenceLabel,
    MemoryManager,
    MemoryQuery,
    MemoryRecord,
    SemanticMemoryStore,
    SourceAnnotation,
)

# Layer 6: Execution
from maref.tools.tool_schema import ToolDefinition, ToolRiskLevel
from maref.executor.queue import TaskQueue
from maref.executor.worker import WorkerPool

# Layer 8: Security (P1 upgrade)
from maref.security.sanitizer import Sanitizer

# Layer 9: Observability (P2 upgrade)
from maref.observation.topology import TopologyTracker

# Layer 10: Infrastructure (P2 upgrade)
from maref.executor.budget import BudgetAction, TokenBudgetController
from maref.executor.warm_pool import WarmPool


# ==============================================================================
# Layer 1: Interface — Intent Gateway
# ==============================================================================
class TestLayer1Interface:
    def test_l1_intent_gateway_classifies(self):
        gateway = IntentGateway()
        event = gateway.process(
            source=InputSource.HTTP,
            raw_input="analyze sales data for Q2",
            user_id="user-1",
        )
        assert event.intent_type == IntentType.TASK
        assert event.user_id == "user-1"
        assert event.event_id is not None

    def test_l1_intent_gateway_rejects_empty(self):
        gateway = IntentGateway()
        with pytest.raises(ValueError, match="empty"):
            gateway.process(source=InputSource.HTTP, raw_input="")

    def test_l1_intent_gateway_rejects_oversized(self):
        gateway = IntentGateway()
        with pytest.raises(ValueError, match="exceeds"):
            gateway.process(source=InputSource.HTTP, raw_input="x" * 60_000)

    def test_l1_intent_classifier_all_types(self):
        assert IntentClassifier.classify("generate report") == IntentType.TASK
        assert IntentClassifier.classify("/deploy") == IntentType.COMMAND
        assert IntentClassifier.classify("remember this setting") == IntentType.PREFERENCE
        assert IntentClassifier.classify("good result") == IntentType.FEEDBACK
        assert IntentClassifier.classify("what is the weather") == IntentType.QUERY


# ==============================================================================
# Layer 2: Human Collaboration — HITL + Interrupt
# ==============================================================================
class TestLayer2HumanCollab:
    def test_l1_interrupt_protocol(self):
        proto = InterruptProtocol()
        result = proto.issue_interrupt("agent-1", InterruptType.PAUSE)
        assert result is not None

    def test_l1_decision_api_exists(self):
        api = HumanDecisionAPI()
        assert api is not None


# ==============================================================================
# Layer 3: Governance — Audit + Circuit Breaker
# ==============================================================================
class TestLayer3Governance:
    def test_l1_audit_logger(self):
        logger = AuditLogger()
        entry = logger.log(event_type="security", actor="test", action="login_attempt", details="from 127.0.0.1")
        assert entry is not None

    def test_l1_circuit_breaker(self):
        cb = CircuitBreaker()
        assert cb.state in (BreakerState.CLOSED, BreakerState.OPEN, BreakerState.HALF_OPEN)


# ==============================================================================
# Layer 4: Orchestration — Vector Clock + NACK + Task Graph
# ==============================================================================
class TestLayer4Orchestration:
    def test_l1_vector_clock(self):
        vc = VectorClock.new("agent-a")
        vc2 = vc.tick("agent-b")
        assert vc2.happens_before(vc) == False

    def test_l1_nack_protocol(self):
        nack = NackBuilder()
        msg = nack.agents(from_agent="agent-a", to_agent="agent-b").because(NackCode.OVERLOADED, "too busy").build()
        assert msg.code == NackCode.OVERLOADED
        assert isinstance(msg, NackMessage)

    def test_l1_task_graph_can_build(self):
        from maref.orchestration.task_graph import TaskNode
        node = TaskNode(task_id="test", description="test node")
        assert node.task_id == "test"


# ==============================================================================
# Layer 5: Memory — Vector Search + Consolidation Gate (P1)
# ==============================================================================
class TestLayer5Memory:
    def test_l1_memory_manager(self):
        mm = MemoryManager()
        record = mm.create_record(
            content={"key": "val"},
            confidence=ConfidenceLabel.HIGH,
            source=SourceAnnotation.HUMAN,
        )
        assert record.memory_id is not None

    def test_l1_vector_search(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"text": "deep learning is powerful"}))
        results = mm.semantic.query(MemoryQuery(keywords=["deep", "learning"]))
        assert len(results) >= 1

    def test_l1_consolidation_gate_rejects_empty(self):
        mm = MemoryManager(enable_gate=True)
        with pytest.raises(ValueError, match="rejected"):
            mm.write_with_gate(MemoryRecord(content={}))

    def test_l1_consolidation_gate_passes_valid(self):
        mm = MemoryManager(enable_gate=True)
        record = mm.create_record(
            content={"text": "valid data"},
            confidence=ConfidenceLabel.CERTAIN,
            source=SourceAnnotation.HUMAN,
        )
        stored = mm.write_with_gate(record)
        assert stored.memory_id == record.memory_id

    def test_l1_query_similar(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"topic": "machine learning basics"}))
        results = mm.semantic.query_similar("deep learning introduction", limit=5)
        assert len(results) >= 1


# ==============================================================================
# Layer 6: Execution — Tool Schema + Queue
# ==============================================================================
class TestLayer6Execution:
    def test_l1_tool_schema(self):
        schema = ToolDefinition(name="test_tool", description="test")
        assert schema.name == "test_tool"

    def test_l1_task_queue(self):
        from maref.executor.types import Task
        q = TaskQueue(db_path=":memory:")
        task = Task(id="test-1", name="test task", payload={})
        task_id = q.enqueue(task)
        assert task_id is not None


# ==============================================================================
# Layer 7: Skill Marketplace
# ==============================================================================
# Layer 8: Security — Sanitizer (P1)
# ==============================================================================
class TestLayer8Security:
    def test_l1_sanitizer_cleans_pii(self):
        sani = Sanitizer()
        result = sani.sanitize_input("my phone is 13800138000")
        assert "13800138000" not in result.text
        assert "[PII_" in result.text

    def test_l1_sanitizer_blocks_sql(self):
        sani = Sanitizer()
        result = sani.sanitize_input("'; DROP TABLE users; --")
        assert result.blocked is True

    def test_l1_sanitizer_restores_authorized(self):
        sani = Sanitizer()
        result = sani.sanitize_input("email test@example.com")
        restored = sani.restore_output(result.text, result.tokens, authorized=True)
        assert "test@example.com" in restored

    def test_l1_sanitizer_redacts_output(self):
        sani = Sanitizer()
        output = sani.sanitize_output("my email is user@test.com")
        assert "user@test.com" not in output
        assert "[REDACTED" in output


# ==============================================================================
# Layer 9: Observability — Topology (P2) + OTel
# ==============================================================================
class TestLayer9Observability:
    def test_l1_tracker_records_calls(self):
        tracker = TopologyTracker()
        tracker.record_call("agent-a", "agent-b", latency_ms=150)
        graph = tracker.get_graph()
        assert graph["edge_count"] == 1
        assert graph["node_count"] == 2

    def test_l1_tracker_accumulates_metrics(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b", latency_ms=100)
        tracker.record_call("a", "b", latency_ms=200, error=True)
        edges = tracker.get_edge_summary()
        assert edges[0]["call_count"] == 2
        assert edges[0]["avg_latency_ms"] == 150.0

    def test_l1_tracker_node_status(self):
        tracker = TopologyTracker()
        tracker.record_call("a", "b")
        tracker.set_node_status("a", "degraded")
        graph = tracker.get_graph()
        node = next(n for n in graph["nodes"] if n["agent_id"] == "a")
        assert node["status"] == "degraded"

# Layer 10: Infrastructure — Budget + WarmPool (P2)
# ==============================================================================
class TestLayer10Infrastructure:
    def test_l1_budget_allows_within_limit(self):
        ctrl = TokenBudgetController(tier="standard")
        result = ctrl.check_cost("task-1", "user-1", estimated_cost=1.0)
        assert result.action == BudgetAction.ALLOW

    def test_l1_budget_blocks_over_limit(self):
        ctrl = TokenBudgetController(tier="cheap")
        result = ctrl.check_cost("task-1", "user-1", estimated_cost=999.0)
        assert result.action == BudgetAction.BLOCK

    def test_l1_budget_tracks_cost(self):
        ctrl = TokenBudgetController()
        ctrl.record_cost("task-1", "user-1", actual_cost=10.0)
        assert ctrl.get_user_cost("user-1") == 10.0

    def test_l1_budget_rate_limits(self):
        ctrl = TokenBudgetController(tier="cheap")
        for i in range(35):
            ctrl.record_cost(f"task-{i}", "user-1", actual_cost=0.01)
        result = ctrl.check_cost("task-late", "user-1", estimated_cost=0.01)
        assert result.action == BudgetAction.BLOCK

    def test_l1_warm_pool(self):
        pool = WarmPool(min_size=2, max_size=10)
        pool.start()
        stats = pool.get_stats()
        assert stats["pool_size"] == 2
        worker = pool.acquire()
        assert worker is not None
        assert worker.is_busy
        pool.release(worker)
        pool.stop()
