from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone

import pytest

from maref.executor.queue import TaskQueue
from maref.executor.scheduler import Scheduler
from maref.executor.types import Task, TaskStatus
from maref.governance.audit_bus import AuditBus, AuditEvent


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


class TestSchedulerBackwardCompatibility:
    """Ensure Scheduler works without an AuditBus (backward compatible)."""

    def test_create_without_bus(self, queue: TaskQueue) -> None:
        s = Scheduler(queue)
        assert s._bus is None
        assert not s.halted
        assert s.faulty_agents == set()

    def test_start_stop_without_bus(self, queue: TaskQueue) -> None:
        s = Scheduler(queue)
        s.start()
        assert s._running is True
        s.stop()
        assert s._running is False

    def test_tick_without_bus(self, queue: TaskQueue) -> None:
        s = Scheduler(queue, tick_interval=0.05)
        task = Task(name="compat")
        s.add_cron_job("compat", "* * * * *", task)
        s.start()
        time.sleep(0.12)
        s.stop()
        # At least one tick may have fired; queue may or may not have tasks
        # depending on timing, but no exception should occur.
        assert not s.halted


class TestSchedulerHaltEvent:
    """GOVERNANCE HALT → stop accepting new tasks, clear queue within 100ms."""

    def test_halt_stops_tick_enqueue(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, tick_interval=0.05, bus=bus)
        task = Task(name="halt-test")
        s.add_cron_job("halt-job", "* * * * *", task)
        s.start()
        time.sleep(0.08)
        # Publish HALT event
        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
        )
        bus.publish(event)
        # After halt, scheduler should be halted
        assert s.halted is True
        # Queue should be cleared
        assert queue.count_tasks() == 0
        s.stop()

    def test_halt_disables_jobs(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        task = Task(name="job-test")
        job_id = s.add_cron_job("job", "* * * * *", task)
        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
        )
        bus.publish(event)
        job = s.get_job(job_id)
        assert job is not None
        assert job.enabled is False
        s.stop()

    def test_halt_clears_within_100ms(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        # Pre-populate queue
        for i in range(10):
            queue.enqueue(Task(name=f"pre-{i}"))
        assert queue.count_tasks() == 10
        start = time.time()
        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
        )
        bus.publish(event)
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 100.0
        assert queue.count_tasks() == 0
        s.stop()

    def test_halt_idempotent(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        event = AuditEvent(
            category="governance",
            action="halt",
            resource="scheduler",
        )
        bus.publish(event)
        bus.publish(event)
        assert s.halted is True
        s.stop()


class TestSchedulerCircuitOpen:
    """CIRCUIT_OPEN → pause task allocation to the faulty Agent."""

    def test_circuit_open_records_agent(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        event = AuditEvent(
            category="operational",
            action="circuit_open",
            metadata={"agent_id": "agent-42"},
        )
        bus.publish(event)
        assert "agent-42" in s.faulty_agents
        s.stop()

    def test_circuit_open_uses_agent_did(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        event = AuditEvent(
            category="operational",
            action="circuit_open",
            agent_did="agent-did-99",
        )
        bus.publish(event)
        assert "agent-did-99" in s.faulty_agents
        s.stop()

    def test_circuit_open_no_agent_id_warns(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        event = AuditEvent(
            category="operational",
            action="circuit_open",
        )
        # Should not raise; just warn
        bus.publish(event)
        assert s.faulty_agents == set()
        s.stop()

    def test_multiple_agents_faulty(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        for i in range(3):
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": f"agent-{i}"},
                )
            )
        assert s.faulty_agents == {"agent-0", "agent-1", "agent-2"}
        s.stop()


class TestSchedulerAgentRecovered:
    """AGENT_RECOVERED → resume task allocation."""

    def test_recovered_removes_agent(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                metadata={"agent_id": "agent-7"},
            )
        )
        assert "agent-7" in s.faulty_agents
        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                metadata={"agent_id": "agent-7"},
            )
        )
        assert "agent-7" not in s.faulty_agents
        s.stop()

    def test_recovered_uses_agent_did(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                agent_did="agent-did-88",
            )
        )
        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                agent_did="agent-did-88",
            )
        )
        assert "agent-did-88" not in s.faulty_agents
        s.stop()

    def test_recovered_unknown_agent_no_error(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        bus.publish(
            AuditEvent(
                category="operational",
                action="agent_recovered",
                metadata={"agent_id": "never-faulty"},
            )
        )
        assert s.faulty_agents == set()
        s.stop()


class TestSchedulerStopUnsubscribes:
    """Stopping the scheduler should unsubscribe from AuditBus topics."""

    def test_stop_clears_subscriptions(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        assert len(s._subscribed_topics) == 3
        s.stop()
        assert s._subscribed_topics == []

    def test_stop_without_bus(self, queue: TaskQueue) -> None:
        s = Scheduler(queue)
        s.start()
        s.stop()
        assert not s._running


class TestSchedulerThreadSafety:
    """Governance state mutations must be thread-safe."""

    def test_concurrent_halt_and_tick(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, tick_interval=0.01, bus=bus)
        task = Task(name="race")
        s.add_cron_job("race", "* * * * *", task)
        s.start()
        time.sleep(0.05)
        for _ in range(50):
            bus.publish(
                AuditEvent(
                    category="governance",
                    action="halt",
                    resource="scheduler",
                )
            )
        time.sleep(0.05)
        s.stop()
        # No exception means thread-safety held
        assert s.halted is True

    def test_concurrent_faulty_updates(self, queue: TaskQueue, bus: AuditBus) -> None:
        s = Scheduler(queue, bus=bus)
        for i in range(100):
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="circuit_open",
                    metadata={"agent_id": f"agent-{i % 10}"},
                )
            )
            bus.publish(
                AuditEvent(
                    category="operational",
                    action="agent_recovered",
                    metadata={"agent_id": f"agent-{i % 10}"},
                )
            )
        assert s.faulty_agents == set()
        s.stop()


class TestGovernanceAwareSchedulerWrapper:
    """Tests for the optional GovernanceAwareScheduler wrapper."""

    def test_wrapper_delegates_properties(self, queue: TaskQueue, bus: AuditBus) -> None:
        from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler

        base = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(base)
        assert gov.halted is False
        assert gov.faulty_agents == set()
        assert gov.running is False
        base.stop()

    def test_wrapper_start_stop(self, queue: TaskQueue, bus: AuditBus) -> None:
        from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler

        base = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(base)
        gov.start()
        assert gov.running is True
        gov.stop()
        assert gov.running is False

    def test_wrapper_is_agent_healthy(self, queue: TaskQueue, bus: AuditBus) -> None:
        from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler

        base = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(base)
        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                metadata={"agent_id": "sick-agent"},
            )
        )
        assert gov.is_agent_healthy("sick-agent") is False
        assert gov.is_agent_healthy("healthy-agent") is True
        base.stop()

    def test_wrapper_filter_tasks(self, queue: TaskQueue, bus: AuditBus) -> None:
        from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler

        base = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(base)
        bus.publish(
            AuditEvent(
                category="operational",
                action="circuit_open",
                metadata={"agent_id": "bad-agent"},
            )
        )
        tasks = [
            Task(name="t1", metadata={"agent_id": "bad-agent"}),
            Task(name="t2", metadata={"agent_id": "good-agent"}),
            Task(name="t3", metadata={}),
        ]

        def resolver(task: Task) -> str | None:
            return task.metadata.get("agent_id")

        healthy = gov.filter_tasks_for_healthy_agents(tasks, resolver)
        assert len(healthy) == 2
        assert {t.name for t in healthy} == {"t2", "t3"}
        base.stop()

    def test_wrapper_job_management(self, queue: TaskQueue, bus: AuditBus) -> None:
        from maref.executor.governance_aware_scheduler import GovernanceAwareScheduler

        base = Scheduler(queue, bus=bus)
        gov = GovernanceAwareScheduler(base)
        task = Task(name="wrapped")
        job_id = gov.add_cron_job("wrapped-job", "0 0 * * *", task)
        assert job_id is not None
        job = gov.get_job(job_id)
        assert job is not None
        assert job.name == "wrapped-job"
        assert gov.remove_job(job_id) is True
        base.stop()
