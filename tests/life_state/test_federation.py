"""Tests for C39: Life State Federation."""

from __future__ import annotations

from maref.life_state.federation import (
    FederationRole,
    LifeStateFederation,
)
from maref.life_state.metadata import LifeStateCapability, LifeStateMetadata


class TestLifeStateFederation:
    def test_join(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        member = fed.join(meta, role=FederationRole.WORKER)
        assert member.state_id == "s1"
        assert member.role == FederationRole.WORKER
        assert fed.get_member("s1") is member

    def test_join_registers_in_registry(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        fed.join(meta)
        assert fed._registry.has("s1")

    def test_leave(self):
        fed = LifeStateFederation()
        fed.join(LifeStateMetadata(state_id="s1"))
        fed.leave("s1")
        assert fed.get_member("s1") is None

    def test_list_by_role(self):
        fed = LifeStateFederation()
        fed.join(LifeStateMetadata(state_id="c1"), role=FederationRole.COORDINATOR)
        fed.join(LifeStateMetadata(state_id="w1"), role=FederationRole.WORKER)
        coordinators = fed.list_by_role(FederationRole.COORDINATOR)
        assert len(coordinators) == 1
        assert coordinators[0].state_id == "c1"

    def test_find_capable(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        meta.add_capability(LifeStateCapability.COMPUTE)
        fed.join(meta)
        capable = fed.find_capable(LifeStateCapability.COMPUTE)
        assert len(capable) == 1

    def test_assign_task(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        meta.add_capability(LifeStateCapability.COMPUTE)
        fed.join(meta)
        task = fed.assign_task("calc", LifeStateCapability.COMPUTE, {"x": 1})
        assert task is not None
        assert task.assigned_to == "s1"
        assert task.status == "pending"

    def test_assign_task_no_candidates(self):
        fed = LifeStateFederation()
        task = fed.assign_task("calc", LifeStateCapability.COMPUTE, {})
        assert task is None

    def test_assign_task_load_balancing(self):
        fed = LifeStateFederation()
        m1 = LifeStateMetadata(state_id="s1")
        m1.add_capability(LifeStateCapability.COMPUTE)
        m2 = LifeStateMetadata(state_id="s2")
        m2.add_capability(LifeStateCapability.COMPUTE)
        fed.join(m1)
        fed.join(m2)
        fed.assign_task("t1", LifeStateCapability.COMPUTE, {})
        t2 = fed.assign_task("t2", LifeStateCapability.COMPUTE, {})
        assert t2.assigned_to == "s2"

    def test_complete_task(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        meta.add_capability(LifeStateCapability.COMPUTE)
        fed.join(meta)
        task = fed.assign_task("calc", LifeStateCapability.COMPUTE, {})
        completed = fed.complete_task(task.task_id)
        assert completed.status == "completed"
        assert fed.get_member("s1").task_count == 0

    def test_get_coordinator(self):
        fed = LifeStateFederation()
        fed.join(LifeStateMetadata(state_id="c1"), role=FederationRole.COORDINATOR)
        coord = fed.get_coordinator()
        assert coord is not None
        assert coord.state_id == "c1"

    def test_get_coordinator_none(self):
        fed = LifeStateFederation()
        assert fed.get_coordinator() is None

    def test_list_tasks(self):
        fed = LifeStateFederation()
        meta = LifeStateMetadata(state_id="s1")
        meta.add_capability(LifeStateCapability.COMPUTE)
        fed.join(meta)
        fed.assign_task("t1", LifeStateCapability.COMPUTE, {})
        tasks = fed.list_tasks("s1")
        assert len(tasks) == 1

    def test_to_dict(self):
        fed = LifeStateFederation()
        fed.join(LifeStateMetadata(state_id="s1"))
        d = fed.to_dict()
        assert d["member_count"] == 1
        assert d["task_count"] == 0
