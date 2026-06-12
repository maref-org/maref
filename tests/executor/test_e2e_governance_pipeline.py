"""T5.5 E2E Scenario Verification — Full Governance Pipeline.

Validates the complete chain:
  CircuitBreaker → AuditBus.publish → Scheduler (HALT / circuit_open / agent_recovered)
  → TaskQueue (clear / filter) → GovernanceAwareScheduler (health checks)

Scenarios:
  S1: Full HALT pipeline — CircuitBreaker trips → AuditBus → Scheduler HALT → Queue cleared
  S2: Circuit Open/Recover cycle — Fault detected → Agent marked faulty → Recovery → Agent healthy
  S3: Multi-agent fault isolation — Multiple circuit opens → Only faulty agents filtered
  S4: HALT + Recovery cycle — HALT → resume → queue accepts new tasks
  S5: Chaos resilience — Concurrent events → System stability → Correct final state
  S6: AuditBus integrity — Events are signed, verifiable, and queryable
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest

from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler
from maref.executor.queue import TaskQueue
from maref.executor.scheduler import Scheduler
from maref.executor.types import Task, TaskStatus
from maref.governance.audit_bus import AuditBus, AuditEvent
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def queue(db_path: str) -> TaskQueue:
    q = TaskQueue(db_path)
    yield q
    q.close()


@pytest.fixture
def bus() -> AuditBus:
    return AuditBus()


@pytest.fixture
def signed_bus() -> AuditBus:
    return AuditBus(hmac_key="e2e-test-hmac-key-2026")


@pytest.fixture
def cb() -> CircuitBreaker:
    return CircuitBreaker(
        max_depth=3,
        max_oscillation_rate=10.0,
        max_consecutive_failures=5,
        cooldown_seconds=0.5,
    )


# ============================================================================
# S1: Full HALT Pipeline
# ============================================================================


class TestScenario1FullHaltPipeline:
    """S1: CircuitBreaker trips → AuditBus → Scheduler HALT → Queue cleared."""

    def test_circuit_breaker_trip_to_halt(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        cb = CircuitBreaker(max_consecutive_failures=3, cooldown_seconds=0.1)
        s = Scheduler(queue, tick_interval=0.05, bus=bus)

        task = Task(name="sensitive")
        s.add_cron_job("sensitive-job", "* * * * *", task)
        s.start()
        time.sleep(0.08)

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.state == BreakerState.OPEN, "Circuit breaker should trip after 3 failures"

        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
            metadata={
                "reason": "circuit_breaker_tripped",
                "breaker_state": cb.state.value,
            },
        )
        bus.publish(event)

        assert s.halted is True
        assert queue.count_tasks() == 0

        s.stop()

    def test_halt_stops_task_generation(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, tick_interval=0.05, bus=bus)
        task = Task(name="should-not-run")
        s.add_cron_job("sensitive-job", "* * * * *", task)
        s.start()

        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
        )
        bus.publish(event)

        queue_count_before = queue.count_tasks()
        time.sleep(0.15)
        queue_count_after = queue.count_tasks()

        assert queue_count_before == 0
        assert queue_count_after == 0

        s.stop()

    def test_halt_idempotent_no_side_effects(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)
        for i in range(5):
            queue.enqueue(Task(name=f"pre-{i}"))
        assert queue.count_tasks() == 5

        bus.publish(AuditEvent(category="governance", action="halt", resource="scheduler"))
        bus.publish(AuditEvent(category="governance", action="halt", resource="scheduler"))
        bus.publish(AuditEvent(category="governance", action="halt", resource="scheduler"))

        assert s.halted is True
        assert queue.count_tasks() == 0

        s.stop()

    def test_halt_time_bound_100ms(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        """HALT event must clear queue within 100ms even under load."""
        s = Scheduler(queue, bus=bus)
        for i in range(200):
            queue.enqueue(Task(name=f"load-{i}"))
        assert queue.count_tasks() == 200

        start = time.time()
        bus.publish(AuditEvent(category="governance", action="halt", resource="scheduler"))
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100.0, f"HALT took {elapsed_ms:.1f}ms, must be < 100ms"
        assert queue.count_tasks() == 0
        s.stop()


# ============================================================================
# S2: Circuit Open / Recover Cycle
# ============================================================================


class TestScenario2CircuitOpenRecover:
    """S2: Fault detected → Agent marked faulty → Recovery → Agent healthy."""

    def test_circuit_open_then_recover(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)

        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                metadata={"agent_id": "agent-alpha"},
            )
        )
        assert "agent-alpha" in s.faulty_agents
        assert s.faulty_agents == {"agent-alpha"}

        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                metadata={"agent_id": "agent-alpha"},
            )
        )
        assert "agent-alpha" not in s.faulty_agents
        assert s.faulty_agents == set()

        s.stop()

    def test_multi_agent_fault_then_selective_recovery(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)

        for agent in ["agent-a", "agent-b", "agent-c"]:
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": agent},
                )
            )

        assert s.faulty_agents == {"agent-a", "agent-b", "agent-c"}

        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                metadata={"agent_id": "agent-b"},
            )
        )

        assert s.faulty_agents == {"agent-a", "agent-c"}

        s.stop()

    def test_governance_aware_filtering(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(s)

        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                metadata={"agent_id": "bad-agent"},
            )
        )

        tasks = [
            Task(name="t-bad", metadata={"agent_id": "bad-agent"}),
            Task(name="t-good", metadata={"agent_id": "good-agent"}),
            Task(name="t-none", metadata={}),
        ]

        def resolver(task: Task) -> str | None:
            return task.metadata.get("agent_id")

        healthy = gov.filter_tasks_for_healthy_agents(tasks, resolver)
        assert len(healthy) == 2
        assert {t.name for t in healthy} == {"t-good", "t-none"}

        s.stop()

    def test_agent_did_field_fallback(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)

        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                agent_did="did:maref:agent-42",
            )
        )
        assert "did:maref:agent-42" in s.faulty_agents

        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                agent_did="did:maref:agent-42",
            )
        )
        assert "did:maref:agent-42" not in s.faulty_agents

        s.stop()


# ============================================================================
# S3: Multi-Agent Fault Isolation
# ============================================================================


class TestScenario3MultiAgentFaultIsolation:
    """S3: Multiple circuit opens → Only faulty agents filtered → Healthy agents unaffected."""

    def test_many_faults_correct_isolation(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(s)

        for i in range(20):
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": f"faulty-{i}"},
                )
            )

        assert len(s.faulty_agents) == 20

        tasks = []
        for i in range(100):
            tasks.append(
                Task(
                    name=f"task-{i}",
                    metadata={
                        "agent_id": f"faulty-{i % 20}" if i < 50 else f"healthy-{i % 5}"
                    },
                )
            )

        def resolver(task: Task) -> str | None:
            return task.metadata.get("agent_id")

        healthy = gov.filter_tasks_for_healthy_agents(tasks, resolver)
        assert len(healthy) == 50

        healthy_agents = {resolver(t) for t in healthy}
        for agent in s.faulty_agents:
            assert agent not in healthy_agents

        s.stop()

    def test_faulty_agents_dont_affect_queue_operations(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)

        for i in range(5):
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": f"faulty-{i}"},
                )
            )

        task = Task(name="normal-task")
        queue.enqueue(task)
        assert queue.count_tasks() == 1

        assert not s.halted

        s.stop()


# ============================================================================
# S4: HALT + Recovery Cycle
# ============================================================================


class TestScenario4HaltRecoveryCycle:
    """S4: HALT → Scheduler stops → (manual clear) → New scheduler → Normal operation."""

    def test_halt_then_new_scheduler_resumes(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s1 = Scheduler(queue, bus=bus)
        task = Task(name="post-recovery")
        s1.add_cron_job("recovery-job", "* * * * *", task)

        bus.publish(
            AuditEvent(category="governance", action="halt", resource="scheduler")
        )
        assert s1.halted is True
        s1.stop()

        s2 = Scheduler(queue, tick_interval=0.05, bus=bus)
        assert s2.halted is False
        task2 = Task(name="new-life")
        s2.add_cron_job("new-job", "* * * * *", task2)
        s2.start()
        time.sleep(0.12)
        s2.stop()

        assert queue.count_tasks() > 0

    def test_jobs_disabled_after_halt(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)
        job_id = s.add_cron_job("important", "0 0 1 1 *", Task(name="yearly"))

        job = s.get_job(job_id)
        assert job is not None
        assert job.enabled is True

        bus.publish(
            AuditEvent(category="governance", action="halt", resource="scheduler")
        )

        job = s.get_job(job_id)
        assert job is not None
        assert job.enabled is False

        s.stop()

    def test_event_signature_preserved_through_halt(
        self, queue: TaskQueue, signed_bus: AuditBus
    ) -> None:
        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
            metadata={"severity": "critical"},
        )
        signed = signed_bus.publish(event)

        assert signed.event_id is not None
        assert signed.timestamp is not None
        assert signed.hmac_signature != ""

        queried = signed_bus.query(category="governance", action="halt", limit=1)
        assert len(queried) == 1
        assert queried[0].event_id == signed.event_id

        integrity = signed_bus.verify_integrity()
        assert integrity["valid_signatures"] >= 1
        assert len(integrity["tampered_entries"]) == 0


# ============================================================================
# S5: Chaos Resilience
# ============================================================================


class TestScenario5ChaosResilience:
    """S5: Concurrent events → System stability → Correct final state."""

    def test_concurrent_halt_and_circuit_events(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, tick_interval=0.02, bus=bus)
        task = Task(name="chaos-target")
        s.add_cron_job("chaos-job", "* * * * *", task)
        s.start()
        time.sleep(0.06)

        errors: list[Exception] = []
        lock = threading.Lock()

        def spam_events():
            try:
                for _ in range(30):
                    bus.publish(
                        AuditEvent(
                            category="governance",
                            action="halt",
                            resource="scheduler",
                        )
                    )
                    bus.publish(
                        AuditEvent(
                            category="operational",
                            action="circuit_open",
                            metadata={"agent_id": f"chaos-agent-{_ % 5}"},
                        )
                    )
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(spam_events) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        time.sleep(0.1)
        s.stop()

        assert len(errors) == 0, f"Chaos test had {len(errors)} errors"
        assert s.halted is True

    def test_rapid_open_close_cycle(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)

        for i in range(50):
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": "oscillating-agent"},
                )
            )
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="agent_recovered",
                    metadata={"agent_id": "oscillating-agent"},
                )
            )

        assert "oscillating-agent" not in s.faulty_agents

        s.stop()

    def test_scheduler_unaffected_by_unrelated_events(
        self, queue: TaskQueue, bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=bus)
        task = Task(name="unrelated-test")
        s.add_cron_job("stable-job", "* * * * *", task)
        s.start()
        time.sleep(0.08)

        for _ in range(20):
            bus.publish(
                AuditEvent(
                    category="audit",
                    action="log",
                    resource="other-service",
                    metadata={"note": "unrelated"},
                )
            )

        assert not s.halted
        assert s.faulty_agents == set()

        s.stop()


# ============================================================================
# S6: AuditBus Integrity
# ============================================================================


class TestScenario6AuditBusIntegrity:
    """S6: Events are signed, verifiable, and queryable through the pipeline."""

    def test_full_pipeline_events_verifiable(
        self, queue: TaskQueue, signed_bus: AuditBus
    ) -> None:
        s = Scheduler(queue, bus=signed_bus)

        halt_event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler-integ-test",
            metadata={"pipeline": "T5.5"},
        )
        signed_halt = signed_bus.publish(halt_event)

        circuit_event = AuditEvent(
            category="operational",
            action="circuit_open",
            metadata={"agent_id": "integ-agent-1"},
        )
        signed_circuit = signed_bus.publish(circuit_event)

        recovered_event = AuditEvent(
            category="operational",
            action="agent_recovered",
            metadata={"agent_id": "integ-agent-1"},
        )
        signed_recovered = signed_bus.publish(recovered_event)

        assert signed_halt.event_id != signed_circuit.event_id != signed_recovered.event_id
        assert signed_halt.hmac_signature != ""
        assert signed_circuit.hmac_signature != ""
        assert signed_recovered.hmac_signature != ""

        integrity = signed_bus.verify_integrity()
        assert integrity["valid_signatures"] >= 3
        assert len(integrity["tampered_entries"]) == 0

        assert s.halted is True
        assert s.faulty_agents == set()

        all_governance = signed_bus.query(category="governance", limit=10)
        assert any(e.event_id == signed_halt.event_id for e in all_governance)

        all_operational = signed_bus.query(category="operational", limit=20)
        assert any(e.event_id == signed_circuit.event_id for e in all_operational)
        assert any(e.event_id == signed_recovered.event_id for e in all_operational)

        s.stop()

    def test_hmac_signing_mandatory_with_key(
        self, queue: TaskQueue, signed_bus: AuditBus
    ) -> None:
        event = AuditEvent(
            category="governance",
            action="test_sign",
            resource="sign-target",
        )
        signed = signed_bus.publish(event)

        assert signed.hmac_signature != ""
        assert len(signed.hmac_signature) == 64

        integrity = signed_bus.verify_integrity()
        assert integrity["valid_signatures"] == 1
        assert integrity["integrity_intact"] is True

    def test_different_keys_produce_different_signatures(
        self, queue: TaskQueue
    ) -> None:
        bus_a = AuditBus(hmac_key="key-alpha")
        bus_b = AuditBus(hmac_key="key-beta")

        event = AuditEvent(
            category="governance",
            action="test_key",
            resource="same-resource",
        )

        signed_a = bus_a.publish(AuditEvent(**event.__dict__))
        signed_b = bus_b.publish(AuditEvent(**event.__dict__))

        assert signed_a.hmac_signature != signed_b.hmac_signature

    def test_query_filtering_pipeline(
        self, queue: TaskQueue, signed_bus: AuditBus
    ) -> None:
        categories_actions = [
            ("governance", "halt"),
            ("governance", "resume"),
            ("operational", "circuit_open"),
            ("operational", "agent_recovered"),
            ("security", "auth_failure"),
            ("security", "auth_success"),
        ]
        for cat, act in categories_actions:
            signed_bus.publish(
                AuditEvent(category=cat, action=act, resource="query-test")
            )

        gov_events = signed_bus.query(category="governance")
        assert all(e.category == "governance" for e in gov_events)
        assert len(gov_events) >= 2

        halt_events = signed_bus.query(action="halt")
        assert len(halt_events) >= 1
        assert all(e.action == "halt" for e in halt_events)

        sec_events = signed_bus.query(category="security")
        assert len(sec_events) >= 2