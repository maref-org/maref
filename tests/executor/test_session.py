from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from maref.executor.queue import TaskQueue
from maref.executor.session import Session, SessionManager


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
def session_manager(queue: TaskQueue) -> SessionManager:
    return SessionManager(queue)


class TestSession:
    def test_default_creation(self) -> None:
        session = Session(id="sess-1")
        assert session.id == "sess-1"
        assert session.status == "active"
        assert session.created_at is not None
        assert session.last_heartbeat is not None
        assert session.closed_at is None
        assert session.ttl == 3600.0
        assert session.metadata == {}
        assert session.task_ids == []

    def test_to_dict(self) -> None:
        session = Session(
            id="sess-1",
            status="active",
            ttl=7200.0,
            metadata={"user": "alice"},
            task_ids=["task-1", "task-2"],
        )
        d = session.to_dict()
        assert d["id"] == "sess-1"
        assert d["status"] == "active"
        assert d["ttl"] == 7200.0
        assert d["metadata"] == {"user": "alice"}
        assert d["task_ids"] == ["task-1", "task-2"]
        assert d["closed_at"] is None

    def test_from_dict_roundtrip(self) -> None:
        original = Session(
            id="sess-r1",
            status="active",
            ttl=1800.0,
            metadata={"env": "test"},
            task_ids=["t1", "t2"],
        )
        d = original.to_dict()
        restored = Session.from_dict(d)
        assert restored.id == original.id
        assert restored.status == original.status
        assert restored.ttl == original.ttl
        assert restored.metadata == original.metadata
        assert restored.task_ids == original.task_ids

    def test_from_dict_minimal(self) -> None:
        session = Session.from_dict({"id": "minimal"})
        assert session.id == "minimal"
        assert session.status == "active"
        assert session.ttl == 3600.0
        assert session.metadata == {}
        assert session.task_ids == []

    def test_to_dict_json_serializable(self) -> None:
        import json

        session = Session(
            id="json-safe",
            metadata={"nested": {"key": "value"}},
            task_ids=["a", "b"],
        )
        d = session.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)
        restored = Session.from_dict(loaded)
        assert restored.id == "json-safe"
        assert restored.metadata == {"nested": {"key": "value"}}


class TestSessionManagerCreate:
    def test_initial_state(self, session_manager: SessionManager) -> None:
        assert session_manager.stats() == {}


class TestSessionManagerCreateSession:
    def test_create_default(self, session_manager: SessionManager) -> None:
        session = session_manager.create_session()
        assert session.id is not None
        assert session.status == "active"
        assert session.ttl == 3600.0

    def test_create_with_custom_id(self, session_manager: SessionManager) -> None:
        session = session_manager.create_session(session_id="my-session")
        assert session.id == "my-session"

    def test_create_with_custom_ttl(self, session_manager: SessionManager) -> None:
        session = session_manager.create_session(ttl=120.0)
        assert session.ttl == 120.0

    def test_create_unique_ids(self, session_manager: SessionManager) -> None:
        s1 = session_manager.create_session()
        s2 = session_manager.create_session()
        assert s1.id != s2.id

    def test_create_overwrite_existing(self, session_manager: SessionManager) -> None:
        s1 = session_manager.create_session(session_id="same-id")
        s1.metadata["key"] = "old"
        session_manager.create_session(session_id="same-id")
        retrieved = session_manager.get_session("same-id")
        assert retrieved is not None
        assert retrieved.metadata != s1.metadata


class TestSessionManagerGetSession:
    def test_get_existing(self, session_manager: SessionManager) -> None:
        created = session_manager.create_session(session_id="get-me")
        retrieved = session_manager.get_session("get-me")
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.status == created.status

    def test_get_nonexistent(self, session_manager: SessionManager) -> None:
        retrieved = session_manager.get_session("does-not-exist")
        assert retrieved is None

    def test_get_returns_deepcopy(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="copy-test", metadata={"key": "original"})
        retrieved = session_manager.get_session("copy-test")
        assert retrieved is not None
        retrieved.metadata["key"] = "mutated"
        original = session_manager.get_session("copy-test")
        assert original is not None
        assert original.metadata["key"] == "original"


class TestSessionManagerHeartbeat:
    def test_update_heartbeat_existing(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="hb-test")
        old_hb = session_manager.get_session("hb-test")
        assert old_hb is not None
        old_time = old_hb.last_heartbeat
        result = session_manager.update_heartbeat("hb-test")
        assert result is True
        updated = session_manager.get_session("hb-test")
        assert updated is not None
        assert updated.last_heartbeat >= old_time

    def test_update_heartbeat_nonexistent(self, session_manager: SessionManager) -> None:
        result = session_manager.update_heartbeat("ghost")
        assert result is False

    def test_heartbeat_changes_timestamp(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="ts-test")
        hb1 = session_manager.get_session("ts-test")
        assert hb1 is not None
        t1 = hb1.last_heartbeat
        session_manager.update_heartbeat("ts-test")
        hb2 = session_manager.get_session("ts-test")
        assert hb2 is not None
        assert hb2.last_heartbeat > t1 or hb2.last_heartbeat >= t1


class TestSessionManagerCheckTimeouts:
    def test_no_expired_sessions(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="alive", ttl=3600.0)
        expired = session_manager.check_timeouts()
        assert expired == []

    def test_single_expired_session(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="expired", ttl=3600.0)
        session_manager._sessions["expired"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        expired = session_manager.check_timeouts()
        assert "expired" in expired
        retrieved = session_manager.get_session("expired")
        assert retrieved is not None
        assert retrieved.status == "expired"

    def test_multiple_expired_sessions(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="s1", ttl=3600.0)
        session_manager.create_session(session_id="s2", ttl=3600.0)
        session_manager.create_session(session_id="s3", ttl=3600.0)
        session_manager._sessions["s1"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        session_manager._sessions["s2"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        expired = session_manager.check_timeouts()
        assert "s1" in expired
        assert "s2" in expired
        assert "s3" not in expired

    def test_already_expired_skipped(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="already-expired", ttl=3600.0)
        session_manager._sessions["already-expired"].status = "expired"
        session_manager._sessions["already-expired"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        expired = session_manager.check_timeouts()
        assert expired == []

    def test_closed_sessions_not_timed_out(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="closed-session", ttl=3600.0)
        session_manager.close_session("closed-session")
        session_manager._sessions["closed-session"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        expired = session_manager.check_timeouts()
        assert "closed-session" not in expired

    def test_ttl_zero_immediately_expires(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="zero-ttl", ttl=0.0)
        expired = session_manager.check_timeouts()
        assert "zero-ttl" in expired


class TestSessionManagerClose:
    def test_close_existing(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="close-me")
        result = session_manager.close_session("close-me")
        assert result is True
        retrieved = session_manager.get_session("close-me")
        assert retrieved is not None
        assert retrieved.status == "closed"
        assert retrieved.closed_at is not None

    def test_close_nonexistent(self, session_manager: SessionManager) -> None:
        result = session_manager.close_session("ghost")
        assert result is False

    def test_close_twice(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="double-close")
        assert session_manager.close_session("double-close") is True
        retrieved1 = session_manager.get_session("double-close")
        assert retrieved1 is not None
        assert retrieved1.status == "closed"
        retrieved2 = session_manager.close_session("double-close")
        assert retrieved2 is True


class TestSessionManagerListSessions:
    def test_list_all(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="a")
        session_manager.create_session(session_id="b")
        session_manager.create_session(session_id="c")
        sessions = session_manager.list_sessions()
        assert len(sessions) == 3

    def test_list_by_status_active(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="active-1")
        session_manager.create_session(session_id="active-2")
        session_manager.create_session(session_id="to-close")
        session_manager.close_session("to-close")
        active = session_manager.list_sessions(status="active")
        assert len(active) == 2
        assert all(s.status == "active" for s in active)

    def test_list_by_status_closed(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="close-me")
        session_manager.close_session("close-me")
        closed = session_manager.list_sessions(status="closed")
        assert len(closed) == 1
        assert closed[0].status == "closed"

    def test_list_returns_deepcopy(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="copy-safe")
        sessions = session_manager.list_sessions()
        sessions[0].metadata["new"] = "value"
        retrieved = session_manager.get_session("copy-safe")
        assert retrieved is not None
        assert "new" not in retrieved.metadata

    def test_list_empty(self, session_manager: SessionManager) -> None:
        sessions = session_manager.list_sessions()
        assert sessions == []

    def test_list_empty_by_status(self, session_manager: SessionManager) -> None:
        sessions = session_manager.list_sessions(status="expired")
        assert sessions == []


class TestSessionManagerRecover:
    def test_recover_existing(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="recover-me", ttl=3600.0)
        session_manager._sessions["recover-me"].metadata = {"task": "important"}
        session_manager._sessions["recover-me"].task_ids = ["t1", "t2"]
        recovered = session_manager.recover_session("recover-me")
        assert recovered is not None
        assert recovered.id == "recover-me"
        assert recovered.status == "active"
        assert recovered.task_ids == ["t1", "t2"]
        assert recovered.metadata == {"task": "important"}
        assert recovered.closed_at is None

    def test_recover_nonexistent(self, session_manager: SessionManager) -> None:
        recovered = session_manager.recover_session("ghost")
        assert recovered is None

    def test_recover_resets_heartbeat(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="hb-reset")
        old_hb = session_manager._sessions["hb-reset"].last_heartbeat
        recovered = session_manager.recover_session("hb-reset")
        assert recovered is not None
        assert recovered.last_heartbeat >= old_hb

    def test_recover_from_closed(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="closed-recover", ttl=3600.0)
        session_manager.close_session("closed-recover")
        recovered = session_manager.recover_session("closed-recover")
        assert recovered is not None
        assert recovered.id == "closed-recover"
        assert recovered.status == "active"
        assert recovered.closed_at is None

    def test_recover_from_expired(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="expired-recover", ttl=3600.0)
        session_manager._sessions["expired-recover"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        session_manager.check_timeouts()
        recovered = session_manager.recover_session("expired-recover")
        assert recovered is not None
        assert recovered.status == "active"

    def test_recover_copies_ttl(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="ttl-copy", ttl=1800.0)
        recovered = session_manager.recover_session("ttl-copy")
        assert recovered is not None
        assert recovered.ttl == 1800.0

    def test_recover_does_not_mutate_original_tasks(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="mutate-test")
        session_manager._sessions["mutate-test"].task_ids = ["t1"]
        recovered = session_manager.recover_session("mutate-test")
        assert recovered is not None
        recovered.task_ids.append("t2")
        original = session_manager.get_session("mutate-test")
        assert original is not None
        assert original.task_ids == ["t1"]


class TestSessionManagerStats:
    def test_stats_empty(self, session_manager: SessionManager) -> None:
        assert session_manager.stats() == {}

    def test_stats_active_only(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="a")
        session_manager.create_session(session_id="b")
        session_manager.create_session(session_id="c")
        stats = session_manager.stats()
        assert stats == {"active": 3}

    def test_stats_multiple_statuses(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="active-1")
        session_manager.create_session(session_id="active-2")
        session_manager.create_session(session_id="closed-1")
        session_manager.create_session(session_id="expired-1")
        session_manager.close_session("closed-1")
        session_manager._sessions["expired-1"].status = "expired"
        stats = session_manager.stats()
        assert stats.get("active") == 2
        assert stats.get("closed") == 1
        assert stats.get("expired") == 1

    def test_stats_with_timeout(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="will-expire", ttl=3600.0)
        session_manager._sessions["will-expire"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        session_manager.check_timeouts()
        stats = session_manager.stats()
        assert stats.get("expired") == 1
        assert stats.get("active", 0) == 0


class TestSessionManagerEdgeCases:
    def test_create_and_get_many_sessions(self, session_manager: SessionManager) -> None:
        ids = []
        for _i in range(100):
            s = session_manager.create_session()
            ids.append(s.id)
        assert len(session_manager.list_sessions()) == 100
        for sid in ids:
            assert session_manager.get_session(sid) is not None

    def test_update_heartbeat_on_expired(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="expired-hb", ttl=3600.0)
        session_manager._sessions["expired-hb"].last_heartbeat = "2020-01-01T00:00:00+00:00"
        session_manager.check_timeouts()
        result = session_manager.update_heartbeat("expired-hb")
        assert result is True
        retrieved = session_manager.get_session("expired-hb")
        assert retrieved is not None
        assert retrieved.status == "expired"

    def test_large_metadata(self, session_manager: SessionManager) -> None:
        large_meta = {"data": "x" * 10000}
        session_manager.create_session(session_id="large-meta", metadata=large_meta)
        retrieved = session_manager.get_session("large-meta")
        assert retrieved is not None
        assert len(retrieved.metadata["data"]) == 10000

    def test_many_task_ids(self, session_manager: SessionManager) -> None:
        task_ids = [f"task-{i}" for i in range(1000)]
        session_manager.create_session(session_id="many-tasks", task_ids=task_ids)
        retrieved = session_manager.get_session("many-tasks")
        assert retrieved is not None
        assert len(retrieved.task_ids) == 1000

    def test_negative_ttl(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="neg-ttl", ttl=-1.0)
        expired = session_manager.check_timeouts()
        assert "neg-ttl" in expired

    def test_heartbeat_interval_property(self, queue: TaskQueue) -> None:
        sm = SessionManager(queue, heartbeat_interval=15.0)
        assert sm._heartbeat_interval == 15.0
        sm2 = SessionManager(queue)
        assert sm2._heartbeat_interval == 30.0

    def test_close_session_sets_closed_at(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="close-ts")
        session_manager.close_session("close-ts")
        retrieved = session_manager.get_session("close-ts")
        assert retrieved is not None
        assert retrieved.closed_at is not None
        assert retrieved.status == "closed"

    def test_list_sessions_does_not_expose_internal_dict(
        self, session_manager: SessionManager
    ) -> None:
        session_manager.create_session(session_id="exposed")
        sessions = session_manager.list_sessions()
        sessions.clear()
        assert session_manager.get_session("exposed") is not None

    def test_recover_preserves_metadata_deepcopy(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="deep-meta", metadata={"nested": {"a": 1}})
        recovered = session_manager.recover_session("deep-meta")
        assert recovered is not None
        recovered.metadata["nested"]["a"] = 2
        original = session_manager.get_session("deep-meta")
        assert original is not None
        assert original.metadata["nested"]["a"] == 1


class TestSessionManagerStoreMethods:
    def test_save_to_store_no_store(self, session_manager: SessionManager) -> None:
        session_manager.create_session(session_id="no-store")
        result = session_manager.save_to_store("no-store")
        assert result is False

    def test_load_from_store_no_store(self, session_manager: SessionManager) -> None:
        result = session_manager.load_from_store("any")
        assert result is None

    def test_save_all_to_store_no_store(self, session_manager: SessionManager) -> None:
        result = session_manager.save_all_to_store()
        assert result == 0

    def test_load_all_from_store_no_store(self, session_manager: SessionManager) -> None:
        result = session_manager.load_all_from_store()
        assert result == 0

    def test_save_to_store_nonexistent_session(self, session_manager: SessionManager) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            from maref.executor.persistent_store import PersistentSessionStore
            store = PersistentSessionStore(Path(tmp) / "sessions.db")
            session_manager._persistent_store = store
            result = session_manager.save_to_store("nonexistent")
            assert result is False
            store.close()

    def test_save_and_load_from_store(self, queue: TaskQueue) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            from maref.executor.persistent_store import PersistentSessionStore
            store = PersistentSessionStore(Path(tmp) / "sessions.db")
            sm = SessionManager(queue, persistent_store=store)
            created = sm.create_session(session_id="store-test", metadata={"k": "v"})
            save_ok = sm.save_to_store("store-test")
            assert save_ok is True
            sm._sessions.clear()
            loaded = sm.load_from_store("store-test")
            assert loaded is not None
            assert loaded.id == "store-test"
            assert loaded.metadata == {"k": "v"}
            store.close()

    def test_save_all_and_load_all_from_store(self, queue: TaskQueue) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            from maref.executor.persistent_store import PersistentSessionStore
            store = PersistentSessionStore(Path(tmp) / "sessions.db")
            sm = SessionManager(queue, persistent_store=store)
            sm.create_session(session_id="a")
            sm.create_session(session_id="b")
            saved = sm.save_all_to_store()
            assert saved == 2
            sm._sessions.clear()
            loaded = sm.load_all_from_store()
            assert loaded == 2
            assert sm.get_session("a") is not None
            assert sm.get_session("b") is not None
            store.close()

    def test_sync_to_store(self, queue: TaskQueue) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            from maref.executor.persistent_store import PersistentSessionStore
            store = PersistentSessionStore(Path(tmp) / "sessions.db")
            sm = SessionManager(queue, persistent_store=store)
            sm.create_session(session_id="sync-me")
            result = sm.sync_to_store()
            assert result["saved"] == 1
            store.close()

    def test_sync_to_store_no_persistent(self, session_manager: SessionManager) -> None:
        result = session_manager.sync_to_store()
        assert result == {"saved": 0, "loaded": 0}

    def test_save_nonexistent_to_store(self, queue: TaskQueue) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            from maref.executor.persistent_store import PersistentSessionStore
            store = PersistentSessionStore(Path(tmp) / "sessions.db")
            sm = SessionManager(queue, persistent_store=store)
            result = sm.save_to_store("ghost")
            assert result is False
            store.close()
