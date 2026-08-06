from __future__ import annotations

import json

from maref.integration.trajectory import (
    TaskTrajectory,
    TrajectoryCollector,
    TrajectoryEvent,
    TrajectoryEventType,
)


class TestTrajectoryEvent:
    def test_create_event(self) -> None:
        event = TrajectoryEvent(
            event_id="e1",
            timestamp=1000.0,
            task_id="t1",
            event_type=TrajectoryEventType.TASK_CREATED,
            actor="agent-1",
            payload={"key": "value"},
        )
        assert event.event_id == "e1"
        assert event.event_type == TrajectoryEventType.TASK_CREATED

    def test_event_serialization_roundtrip(self) -> None:
        event = TrajectoryEvent(
            event_id="e1",
            timestamp=1000.0,
            task_id="t1",
            event_type=TrajectoryEventType.DELEGATION_SENT,
            actor="agent-1",
            payload={"target": "agent-2"},
        )
        d = event.to_dict()
        event2 = TrajectoryEvent.from_dict(d)
        assert event2.event_id == "e1"
        assert event2.event_type == TrajectoryEventType.DELEGATION_SENT
        assert event2.payload["target"] == "agent-2"


class TestTaskTrajectory:
    def test_create_trajectory(self) -> None:
        traj = TaskTrajectory(
            task_id="t1",
            description="test task",
            created_at=1000.0,
        )
        assert traj.task_id == "t1"
        assert traj.final_state is None

    def test_trajectory_serialization_roundtrip(self) -> None:
        traj = TaskTrajectory(
            task_id="t1",
            description="test task",
            created_at=1000.0,
            events=[
                TrajectoryEvent(
                    event_id="e1",
                    timestamp=1000.0,
                    task_id="t1",
                    event_type=TrajectoryEventType.TASK_CREATED,
                    actor="agent-1",
                ),
            ],
            delegations=[{"target": "agent-2", "delegated_at": 1001.0}],
            final_state="completed",
            completed_at=2000.0,
        )
        d = traj.to_dict()
        traj2 = TaskTrajectory.from_dict(d)
        assert traj2.task_id == "t1"
        assert traj2.final_state == "completed"
        assert len(traj2.events) == 1
        assert len(traj2.delegations) == 1


class TestTrajectoryCollector:
    def test_start_task(self) -> None:
        collector = TrajectoryCollector(agent_id="agent-1")
        traj = collector.start_task("t1", "test task")
        assert traj.task_id == "t1"
        assert traj.description == "test task"
        assert len(traj.events) == 1
        assert traj.events[0].event_type == TrajectoryEventType.TASK_CREATED

    def test_complete_task(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "test")
        collector.complete_task("t1", final_state="completed")
        traj = collector.get_trajectory("t1")
        assert traj is not None
        assert traj.final_state == "completed"
        assert traj.completed_at is not None
        assert any(e.event_type == TrajectoryEventType.TASK_COMPLETED for e in traj.events)

    def test_complete_nonexistent_task_does_nothing(self) -> None:
        collector = TrajectoryCollector()
        collector.complete_task("nonexistent", "failed")

    def test_record_event(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "test")
        collector.record_event(
            "t1",
            TrajectoryEventType.TASK_STATE_CHANGED,
            actor="agent-1",
            payload={"from": "pending", "to": "running"},
        )
        traj = collector.get_trajectory("t1")
        assert traj is not None
        assert any(
            e.event_type == TrajectoryEventType.TASK_STATE_CHANGED for e in traj.events
        )

    def test_record_event_defaults_payload_to_empty_dict(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "test")
        collector.record_event(
            "t1",
            TrajectoryEventType.TASK_STATE_CHANGED,
            actor="agent-1",
        )
        traj = collector.get_trajectory("t1")
        assert traj is not None
        event = next(e for e in traj.events if e.event_type == TrajectoryEventType.TASK_STATE_CHANGED)
        assert event.payload == {}

    def test_record_event_nonexistent_task_does_nothing(self) -> None:
        collector = TrajectoryCollector()
        collector.record_event(
            "nonexistent",
            TrajectoryEventType.TASK_STATE_CHANGED,
            actor="agent-1",
        )

    def test_record_message(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "test")
        collector.record_message(
            "t1",
            direction="sent",
            sender="agent-1",
            recipient="agent-2",
            content="hello",
        )
        traj = collector.get_trajectory("t1")
        assert traj is not None
        msg_events = [e for e in traj.events if e.event_type == TrajectoryEventType.MESSAGE_EXCHANGED]
        assert len(msg_events) == 1
        assert msg_events[0].payload["sender"] == "agent-1"
        assert msg_events[0].payload["content_length"] == 5

    def test_record_message_nonexistent_task_does_nothing(self) -> None:
        collector = TrajectoryCollector()
        collector.record_message("nonexistent", "sent", "a1", "a2", "hello")

    def test_record_delegation(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "test")
        collector.record_delegation("t1", "http://agent-2:9000")
        traj = collector.get_trajectory("t1")
        assert traj is not None
        assert len(traj.delegations) == 1
        assert traj.delegations[0]["target_agent_url"] == "http://agent-2:9000"
        assert any(
            e.event_type == TrajectoryEventType.DELEGATION_SENT for e in traj.events
        )

    def test_record_delegation_nonexistent_task_does_nothing(self) -> None:
        collector = TrajectoryCollector()
        collector.record_delegation("nonexistent", "http://agent-2:9000")

    def test_single_vs_multi_agent_trajectories(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("single", "single agent task")
        collector.start_task("multi", "multi agent task")
        collector.record_delegation("multi", "http://agent-2:9000")
        collector.complete_task("single")
        collector.complete_task("multi")

        single = collector.get_single_agent_trajectories()
        multi = collector.get_multi_agent_trajectories()
        assert len(single) == 1
        assert single[0].task_id == "single"
        assert len(multi) == 1
        assert multi[0].task_id == "multi"

    def test_get_all_trajectories(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("t1", "task 1")
        collector.start_task("t2", "task 2")
        all_traj = collector.get_all_trajectories()
        assert len(all_traj) == 2

    def test_export_json(self) -> None:
        collector = TrajectoryCollector(agent_id="agent-1")
        collector.start_task("t1", "test task")
        collector.complete_task("t1", "completed")
        json_str = collector.export_json()
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["task_id"] == "t1"

    def test_export_single_multi_json(self) -> None:
        collector = TrajectoryCollector()
        collector.start_task("single", "single task")
        collector.start_task("multi", "multi task")
        collector.record_delegation("multi", "http://a2")

        single_json = collector.export_single_agent_json()
        multi_json = collector.export_multi_agent_json()

        single_data = json.loads(single_json)
        multi_data = json.loads(multi_json)
        assert len(single_data) == 1
        assert single_data[0]["task_id"] == "single"
        assert len(multi_data) == 1
        assert multi_data[0]["task_id"] == "multi"

    def test_get_trajectory_nonexistent(self) -> None:
        collector = TrajectoryCollector()
        assert collector.get_trajectory("nonexistent") is None
