from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from maref.executor.checkpointer import Checkpointer, Snapshot
from maref.executor.queue import TaskQueue
from maref.executor.types import Task, TaskPriority, TaskStatus


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def queue_db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def queue(queue_db_path: str) -> TaskQueue:
    q = TaskQueue(queue_db_path)
    yield q
    q.close()


@pytest.fixture
def checkpointer(queue: TaskQueue, db_path: str) -> Checkpointer:
    c = Checkpointer(queue, db_path)
    yield c
    c.close()


class TestCheckpointerCreate:
    def test_create_with_temp_db(self, checkpointer: Checkpointer) -> None:
        snapshots = checkpointer.list_snapshots()
        assert snapshots == []

    def test_create_with_custom_path(self, queue: TaskQueue, db_path: str) -> None:
        c = Checkpointer(queue, db_path)
        assert c.list_snapshots() == []
        c.close()

    def test_reopen_persistence(self, queue: TaskQueue, db_path: str) -> None:
        c1 = Checkpointer(queue, db_path)
        sid = c1.create_snapshot("persist-test")
        c1.close()
        c2 = Checkpointer(queue, db_path)
        snapshot = c2.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.label == "persist-test"
        c2.close()

    def test_multiple_checkpointers_same_db(self, queue: TaskQueue, db_path: str) -> None:
        c1 = Checkpointer(queue, db_path)
        c2 = Checkpointer(queue, db_path)
        sid = c1.create_snapshot("multi")
        snapshot = c2.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.label == "multi"
        c1.close()
        c2.close()


class TestCheckpointerCreateSnapshot:
    def test_create_snapshot_with_tasks(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t1 = Task(name="task-a")
        t2 = Task(name="task-b")
        queue.enqueue(t1)
        queue.enqueue(t2)
        sid = checkpointer.create_snapshot("test-snapshot")
        assert isinstance(sid, str)
        assert len(sid) > 0
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.label == "test-snapshot"
        assert snapshot.task_count == 2

    def test_create_snapshot_empty_queue(self, checkpointer: Checkpointer) -> None:
        sid = checkpointer.create_snapshot("empty")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.task_count == 0
        assert snapshot.status_summary == {}

    def test_create_snapshot_with_mixed_statuses(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t1 = Task(name="queued")
        t2 = Task(name="running")
        t3 = Task(name="completed")
        queue.enqueue(t1)
        queue.enqueue(t2)
        queue.enqueue(t3)
        queue.update_status(t2.id, TaskStatus.RUNNING)
        queue.update_status(t3.id, TaskStatus.COMPLETED)
        sid = checkpointer.create_snapshot("mixed")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.task_count == 3
        assert snapshot.status_summary.get("queued") == 1
        assert snapshot.status_summary.get("running") == 1
        assert snapshot.status_summary.get("completed") == 1

    def test_create_snapshot_default_label(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="default-label"))
        sid = checkpointer.create_snapshot()
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.label == ""

    def test_create_snapshot_unique_ids(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="a"))
        sid1 = checkpointer.create_snapshot("s1")
        sid2 = checkpointer.create_snapshot("s2")
        assert sid1 != sid2

    def test_create_snapshot_checksum_present(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="checksum-test"))
        sid = checkpointer.create_snapshot("checksum")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert len(snapshot.checksum) == 64

    def test_create_snapshot_data_serializes_tasks(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t = Task(name="serialize-me", priority=TaskPriority.HIGH, tags=["urgent"])
        queue.enqueue(t)
        sid = checkpointer.create_snapshot("serialize")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        tasks_data = json.loads(snapshot.data)
        assert len(tasks_data) == 1
        assert tasks_data[0]["name"] == "serialize-me"
        assert tasks_data[0]["tags"] == ["urgent"]


class TestCheckpointerRestore:
    def test_restore_snapshot(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t = Task(name="restore-me")
        queue.enqueue(t)
        sid = checkpointer.create_snapshot("restore-test")
        queue.delete(t.id)
        assert queue.list_tasks() == []
        result = checkpointer.restore(sid)
        assert result is True
        tasks = queue.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "restore-me"

    def test_restore_preserves_running_tasks(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        running = Task(name="running-task")
        queued = Task(name="queued-task")
        queue.enqueue(running)
        queue.enqueue(queued)
        queue.update_status(running.id, TaskStatus.RUNNING)
        sid = checkpointer.create_snapshot("preserve-running")
        queue.clear()
        queue.enqueue(Task(name="new-task"))
        queue.update_status(running.id, TaskStatus.RUNNING)
        result = checkpointer.restore(sid)
        assert result is True
        tasks = queue.list_tasks()
        task_names = {t.name for t in tasks}
        assert "restore-me" not in task_names

    def test_restore_nonexistent_snapshot(self, checkpointer: Checkpointer) -> None:
        result = checkpointer.restore("nonexistent-id")
        assert result is False

    def test_restore_multiple_tasks(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        for i in range(5):
            queue.enqueue(Task(name=f"restore-{i}"))
        sid = checkpointer.create_snapshot("multi-restore")
        queue.clear()
        result = checkpointer.restore(sid)
        assert result is True
        tasks = queue.list_tasks()
        assert len(tasks) == 5
        names = sorted(t.name for t in tasks)
        assert names == [f"restore-{i}" for i in range(5)]

    def test_restore_skips_running_tasks_in_current_queue(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t = Task(name="should-persist")
        queue.enqueue(t)
        sid = checkpointer.create_snapshot("skip-running")
        queue.update_status(t.id, TaskStatus.RUNNING)
        result = checkpointer.restore(sid)
        assert result is True
        tasks = queue.list_tasks()
        task_ids = {task.id for task in tasks}
        assert t.id in task_ids

    def test_restore_empty_snapshot(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        sid = checkpointer.create_snapshot("empty-restore")
        queue.enqueue(Task(name="to-clear"))
        result = checkpointer.restore(sid)
        assert result is True
        tasks = queue.list_tasks()
        assert len(tasks) == 0


class TestCheckpointerListSnapshots:
    def test_list_snapshots_empty(self, checkpointer: Checkpointer) -> None:
        snapshots = checkpointer.list_snapshots()
        assert snapshots == []

    def test_list_snapshots_multiple(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="list-test"))
        sid1 = checkpointer.create_snapshot("first")
        sid2 = checkpointer.create_snapshot("second")
        sid3 = checkpointer.create_snapshot("third")
        snapshots = checkpointer.list_snapshots()
        assert len(snapshots) == 3
        ids = [s.id for s in snapshots]
        assert sid3 in ids
        assert sid2 in ids
        assert sid1 in ids

    def test_list_snapshots_ordered_by_recency(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="order-test"))
        sid1 = checkpointer.create_snapshot("oldest")
        sid2 = checkpointer.create_snapshot("middle")
        sid3 = checkpointer.create_snapshot("newest")
        snapshots = checkpointer.list_snapshots()
        assert snapshots[0].id == sid3
        assert snapshots[1].id == sid2
        assert snapshots[2].id == sid1

    def test_list_snapshots_limit(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="limit-test"))
        for _ in range(5):
            checkpointer.create_snapshot("batch")
        snapshots = checkpointer.list_snapshots(limit=3)
        assert len(snapshots) == 3

    def test_list_snapshots_returns_snapshot_objects(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="type-test"))
        checkpointer.create_snapshot("type-check")
        snapshots = checkpointer.list_snapshots()
        assert len(snapshots) == 1
        s = snapshots[0]
        assert isinstance(s, Snapshot)
        assert isinstance(s.id, str)
        assert isinstance(s.task_count, int)
        assert isinstance(s.status_summary, dict)


class TestCheckpointerGetSnapshot:
    def test_get_existing_snapshot(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="get-test"))
        sid = checkpointer.create_snapshot("get-me")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.id == sid
        assert snapshot.label == "get-me"

    def test_get_nonexistent_snapshot(self, checkpointer: Checkpointer) -> None:
        snapshot = checkpointer.get_snapshot("i-do-not-exist")
        assert snapshot is None

    def test_get_snapshot_has_all_fields(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="field-test"))
        sid = checkpointer.create_snapshot("fields")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.id == sid
        assert snapshot.label == "fields"
        assert snapshot.created_at != ""
        assert snapshot.task_count == 1
        assert isinstance(snapshot.status_summary, dict)
        assert snapshot.checksum != ""
        assert snapshot.data != ""


class TestCheckpointerDeleteSnapshot:
    def test_delete_existing_snapshot(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="delete-test"))
        sid = checkpointer.create_snapshot("delete-me")
        result = checkpointer.delete_snapshot(sid)
        assert result is True
        assert checkpointer.get_snapshot(sid) is None

    def test_delete_nonexistent_snapshot(self, checkpointer: Checkpointer) -> None:
        result = checkpointer.delete_snapshot("ghost")
        assert result is False

    def test_delete_reduces_list_count(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="count-test"))
        s2 = checkpointer.create_snapshot("a")
        checkpointer.create_snapshot("b")
        checkpointer.create_snapshot("c")
        assert len(checkpointer.list_snapshots()) == 3
        checkpointer.delete_snapshot(s2)
        assert len(checkpointer.list_snapshots()) == 2


class TestCheckpointerVerifyIntegrity:
    def test_verify_integrity_valid(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="integrity-test"))
        sid = checkpointer.create_snapshot("valid")
        assert checkpointer.verify_integrity(sid) is True

    def test_verify_integrity_tampered_checksum(self, queue: TaskQueue, checkpointer: Checkpointer, db_path: str) -> None:
        queue.enqueue(Task(name="tamper-me"))
        sid = checkpointer.create_snapshot("tamper")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE snapshots SET checksum = ? WHERE id = ?",
            ("0" * 64, sid),
        )
        conn.commit()
        conn.close()
        assert checkpointer.verify_integrity(sid) is False

    def test_verify_integrity_tampered_data(self, queue: TaskQueue, checkpointer: Checkpointer, db_path: str) -> None:
        queue.enqueue(Task(name="data-tamper"))
        sid = checkpointer.create_snapshot("data-tamper")
        conn = sqlite3.connect(db_path)
        original = conn.execute(
            "SELECT data FROM snapshots WHERE id = ?", (sid,)
        ).fetchone()[0]
        tampered_data = original.replace("data-tamper", "tampered!")
        conn.execute(
            "UPDATE snapshots SET data = ? WHERE id = ?",
            (tampered_data, sid),
        )
        conn.commit()
        conn.close()
        assert checkpointer.verify_integrity(sid) is False

    def test_verify_integrity_nonexistent(self, checkpointer: Checkpointer) -> None:
        assert checkpointer.verify_integrity("ghost") is False

    def test_verify_integrity_empty_snapshot(self, checkpointer: Checkpointer) -> None:
        sid = checkpointer.create_snapshot("empty-integrity")
        assert checkpointer.verify_integrity(sid) is True


class TestCheckpointerPrune:
    def test_prune_removes_old_snapshots(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="prune-test"))
        sids = []
        for i in range(5):
            sids.append(checkpointer.create_snapshot(f"s{i}"))
        deleted = checkpointer.prune(keep=2)
        assert deleted == 3
        snapshots = checkpointer.list_snapshots()
        assert len(snapshots) == 2

    def test_prune_keeps_recent(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="prune-recent"))
        sids = []
        for i in range(5):
            sids.append(checkpointer.create_snapshot(f"s{i}"))
        checkpointer.prune(keep=2)
        remaining = checkpointer.list_snapshots()
        remaining_ids = {s.id for s in remaining}
        assert sids[3] in remaining_ids
        assert sids[4] in remaining_ids
        assert sids[0] not in remaining_ids
        assert sids[1] not in remaining_ids

    def test_prune_nothing_to_delete(self, checkpointer: Checkpointer) -> None:
        deleted = checkpointer.prune(keep=10)
        assert deleted == 0

    def test_prune_fewer_than_keep(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="few"))
        for i in range(3):
            checkpointer.create_snapshot(f"s{i}")
        deleted = checkpointer.prune(keep=10)
        assert deleted == 0
        assert len(checkpointer.list_snapshots()) == 3

    def test_prune_exact_keep(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="exact"))
        for i in range(3):
            checkpointer.create_snapshot(f"s{i}")
        deleted = checkpointer.prune(keep=3)
        assert deleted == 0
        assert len(checkpointer.list_snapshots()) == 3

    def test_prune_zero_keep(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="zero"))
        for i in range(3):
            checkpointer.create_snapshot(f"s{i}")
        deleted = checkpointer.prune(keep=0)
        assert deleted == 3
        assert len(checkpointer.list_snapshots()) == 0


class TestCheckpointerEdgeCases:
    def test_create_snapshot_with_many_tasks(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        for i in range(50):
            queue.enqueue(Task(name=f"bulk-{i}", payload={"index": i}))
        sid = checkpointer.create_snapshot("bulk")
        snapshot = checkpointer.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.task_count == 50

    def test_create_twice_with_same_label(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        queue.enqueue(Task(name="dup-label"))
        sid1 = checkpointer.create_snapshot("duplicate")
        sid2 = checkpointer.create_snapshot("duplicate")
        assert sid1 != sid2
        snapshots = checkpointer.list_snapshots()
        assert len(snapshots) == 2

    def test_restore_snapshot_twice(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t = Task(name="double-restore")
        queue.enqueue(t)
        sid = checkpointer.create_snapshot("double")
        queue.clear()
        checkpointer.restore(sid)
        checkpointer.restore(sid)
        tasks = queue.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "double-restore"

    def test_close_and_reopen_checkpointer(self, queue: TaskQueue, db_path: str) -> None:
        c1 = Checkpointer(queue, db_path)
        c1.create_snapshot("close-reopen")
        c1.close()
        c2 = Checkpointer(queue, db_path)
        snapshots = c2.list_snapshots()
        assert len(snapshots) == 1
        c2.close()

    def test_snapshot_checksum_deterministic(self, queue: TaskQueue, checkpointer: Checkpointer) -> None:
        t = Task(name="deterministic")
        queue.enqueue(t)
        q2 = TaskQueue(queue._db_path)
        c2 = Checkpointer(q2, checkpointer._db_path)
        sid1 = checkpointer.create_snapshot("det")
        sid2 = c2.create_snapshot("det")
        s1 = checkpointer.get_snapshot(sid1)
        s2 = c2.get_snapshot(sid2)
        assert s1 is not None
        assert s2 is not None
        assert s1.data == s2.data
        assert s1.checksum == s2.checksum
        c2.close()
        q2.close()
