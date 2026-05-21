"""Integration tests for C40: Life State full-stack integration."""

from __future__ import annotations

from maref.life_state.federation import FederationRole, LifeStateFederation
from maref.life_state.health import HealthStatus
from maref.life_state.lifecycle import LifeCycleManager, LifecyclePhase
from maref.life_state.metadata import LifeStateCapability, LifeStateMetadata, LifeStateType
from maref.life_state.messaging import MessageBus, MessageType
from maref.life_state.registry import LifeStateRegistry
from maref.life_state.resources import ResourceMonitor, ResourceQuota, ResourceType, ResourceUsage
from maref.life_state.sandbox import LifeStateSandbox, Permission
from maref.life_state.state_machine import LifeState


class TestFullStackIntegration:
    def test_end_to_end_lifecycle(self):
        mgr = LifeCycleManager()
        meta = LifeStateMetadata(state_id="agent-1", state_type=LifeStateType.AGENT)
        meta.add_capability(LifeStateCapability.COMPUTE)
        meta.add_capability(LifeStateCapability.COMMUNICATE)

        mgr.register_entity(meta)
        assert mgr.get_state("agent-1") == LifeState.BIRTH

        mgr.activate("agent-1")
        assert mgr.get_state("agent-1") == LifeState.ACTIVE

        mgr.health_check("agent-1", "latency_ms", 500.0)
        assert mgr.get_state("agent-1") == LifeState.DEGRADED

        mgr.recover("agent-1")
        assert mgr.get_state("agent-1") == LifeState.ACTIVE

        mgr.terminate("agent-1")
        assert mgr.get_state("agent-1") == LifeState.TERMINATED

    def test_registry_and_federation_integration(self):
        registry = LifeStateRegistry()
        fed = LifeStateFederation(registry=registry)

        meta1 = LifeStateMetadata(state_id="worker-1")
        meta1.add_capability(LifeStateCapability.COMPUTE)
        meta2 = LifeStateMetadata(state_id="worker-2")
        meta2.add_capability(LifeStateCapability.COMPUTE)

        fed.join(meta1, role=FederationRole.WORKER)
        fed.join(meta2, role=FederationRole.WORKER)

        assert registry.count() == 2

        task = fed.assign_task("calc", LifeStateCapability.COMPUTE, {"expr": "1+1"})
        assert task is not None
        assert task.assigned_to in ("worker-1", "worker-2")

    def test_messaging_and_sandbox_integration(self):
        bus = MessageBus()
        sandbox = LifeStateSandbox()

        sandbox.grant("agent-a", Permission.NETWORK)
        sandbox.grant("agent-b", Permission.NETWORK)

        received_a: list = []
        received_b: list = []
        bus.subscribe("agent-a", lambda m: received_a.append(m))
        bus.subscribe("agent-b", lambda m: received_b.append(m))

        bus.broadcast("coordinator", MessageType.EVENT, {"type": "heartbeat"})
        assert len(received_a) == 1
        assert len(received_b) == 1

        assert sandbox.check("agent-a", Permission.NETWORK)
        assert sandbox.get_denied_count("agent-a") == 0

    def test_health_monitoring_with_lifecycle(self):
        mgr = LifeCycleManager()
        mgr.register_entity(LifeStateMetadata(state_id="svc-1"))
        mgr.activate("svc-1")

        mgr.health_check("svc-1", "cpu_percent", 30.0)
        mgr.health_check("svc-1", "memory_percent", 40.0)
        assert mgr._health.get_status("svc-1") == HealthStatus.HEALTHY

        mgr.health_check("svc-1", "cpu_percent", 95.0)
        mgr.health_check("svc-1", "memory_percent", 95.0)
        mgr.health_check("svc-1", "latency_ms", 500.0)
        assert mgr.get_state("svc-1") == LifeState.DEGRADED

    def test_resource_monitoring_with_quota(self):
        monitor = ResourceMonitor()
        monitor.set_quota(ResourceQuota(state_id="pod-1", cpu_limit=100.0))

        monitor.record(ResourceUsage("pod-1", ResourceType.CPU, 50.0, 100.0))
        assert monitor.check_quota("pod-1", ResourceType.CPU, 30.0) is True

        monitor.record(ResourceUsage("pod-1", ResourceType.CPU, 90.0, 100.0))
        assert monitor.check_quota("pod-1", ResourceType.CPU, 20.0) is False
        assert len(monitor.get_alerts()) == 0

    def test_federation_task_distribution(self):
        fed = LifeStateFederation()
        for i in range(3):
            meta = LifeStateMetadata(state_id=f"worker-{i}")
            meta.add_capability(LifeStateCapability.COMPUTE)
            fed.join(meta, role=FederationRole.WORKER)

        tasks = []
        for i in range(6):
            task = fed.assign_task(f"job-{i}", LifeStateCapability.COMPUTE, {"id": i})
            tasks.append(task)

        assert all(t is not None for t in tasks)
        task_counts = {}
        for t in tasks:
            task_counts[t.assigned_to] = task_counts.get(t.assigned_to, 0) + 1
        assert max(task_counts.values()) <= 3

    def test_lifecycle_hooks_integration(self):
        mgr = LifeCycleManager()
        events: list[str] = []
        mgr.add_hook(LifecyclePhase.BIRTH, lambda sid: events.append(f"birth:{sid}"))
        mgr.add_hook(LifecyclePhase.ACTIVATE, lambda sid: events.append(f"activate:{sid}"))
        mgr.add_hook(LifecyclePhase.DEGRADE, lambda sid: events.append(f"degrade:{sid}"))
        mgr.add_hook(LifecyclePhase.RECOVER, lambda sid: events.append(f"recover:{sid}"))
        mgr.add_hook(LifecyclePhase.TERMINATE, lambda sid: events.append(f"terminate:{sid}"))

        mgr.register_entity(LifeStateMetadata(state_id="hooked"))
        mgr.activate("hooked")
        mgr.degrade("hooked")
        mgr.recover("hooked")
        mgr.terminate("hooked")

        assert events == [
            "birth:hooked",
            "activate:hooked",
            "degrade:hooked",
            "recover:hooked",
            "terminate:hooked",
        ]

    def test_multi_entity_communication(self):
        bus = MessageBus()
        messages: list = []
        bus.subscribe_global(lambda m: messages.append((m.sender_id, m.msg_type.value)))

        for i in range(5):
            bus.broadcast(f"agent-{i}", MessageType.HEARTBEAT, {"seq": i})

        assert len(messages) == 5
        assert all(m[1] == "heartbeat" for m in messages)

    def test_sandbox_permission_denial_tracking(self):
        sandbox = LifeStateSandbox()
        sandbox.register("restricted")
        sandbox.grant("restricted", Permission.READ)

        assert sandbox.check("restricted", Permission.READ) is True
        assert sandbox.check("restricted", Permission.WRITE) is False
        assert sandbox.check("restricted", Permission.EXECUTE) is False
        assert sandbox.get_denied_count("restricted") == 2

    def test_full_stack_complex_scenario(self):
        registry = LifeStateRegistry()
        mgr = LifeCycleManager(registry=registry)
        fed = LifeStateFederation(registry=registry)
        bus = MessageBus()
        sandbox = LifeStateSandbox()

        meta = LifeStateMetadata(state_id="complex-agent")
        meta.add_capability(LifeStateCapability.COMPUTE)
        meta.add_capability(LifeStateCapability.COMMUNICATE)

        mgr.register_entity(meta)
        mgr.activate("complex-agent")
        fed.join(meta, role=FederationRole.WORKER)
        sandbox.grant("complex-agent", Permission.EXECUTE)
        sandbox.grant("complex-agent", Permission.NETWORK)

        task = fed.assign_task("analysis", LifeStateCapability.COMPUTE, {"data": [1, 2, 3]})
        assert task is not None
        assert task.assigned_to == "complex-agent"

        bus.broadcast("complex-agent", MessageType.EVENT, {"task": task.task_id})
        assert bus.count() == 1

        mgr.health_check("complex-agent", "latency_ms", 50.0)
        assert mgr._health.get_status("complex-agent") == HealthStatus.HEALTHY

        assert sandbox.check("complex-agent", Permission.EXECUTE)
        assert mgr.get_state("complex-agent") == LifeState.ACTIVE

        mgr.terminate("complex-agent")
        assert mgr.get_state("complex-agent") == LifeState.TERMINATED
