from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from maref.executor.persistent_store import PersistentSessionStore
from maref.executor.session import Session


@pytest.fixture
def db_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def store(db_path: Path) -> PersistentSessionStore:
    s = PersistentSessionStore(db_path)
    yield s
    s.close()


class TestPersistentSessionStoreCreate:
    def test_create_with_temp_db(self, store: PersistentSessionStore) -> None:
        assert store.db_path.exists()
        assert store._conn is not None

    def test_create_with_nonexistent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "sessions.db"
            store = PersistentSessionStore(path)
            assert path.exists()
            store.close()

    def test_reopen_persistence(self, db_path: Path) -> None:
        s1 = PersistentSessionStore(db_path)
        session = Session(id="persist-me", status="active")
        s1.save_session(session)
        s1.close()
        s2 = PersistentSessionStore(db_path)
        loaded = s2.load_session("persist-me")
        assert loaded is not None
        assert loaded.id == "persist-me"
        assert loaded.status == "active"
        s2.close()


class TestPersistentSessionStoreSave:
    def test_save_session(self, store: PersistentSessionStore) -> None:
        session = Session(id="save-test", status="active", ttl=7200.0)
        result = store.save_session(session)
        assert result is True

    def test_save_session_with_metadata(self, store: PersistentSessionStore) -> None:
        session = Session(
            id="meta-test",
            metadata={"user": "alice", "env": "prod"},
            task_ids=["t1", "t2"],
        )
        store.save_session(session)
        loaded = store.load_session("meta-test")
        assert loaded is not None
        assert loaded.metadata == {"user": "alice", "env": "prod"}
        assert loaded.task_ids == ["t1", "t2"]

    def test_save_overwrite_existing(self, store: PersistentSessionStore) -> None:
        s1 = Session(id="overwrite", status="active", metadata={"v": 1})
        store.save_session(s1)
        s2 = Session(id="overwrite", status="closed", metadata={"v": 2})
        store.save_session(s2)
        loaded = store.load_session("overwrite")
        assert loaded is not None
        assert loaded.status == "closed"
        assert loaded.metadata == {"v": 2}

    def test_save_invalid_id(self, store: PersistentSessionStore) -> None:
        result = store.save_session(Session(id="valid"))
        assert result is True


class TestPersistentSessionStoreLoad:
    def test_load_existing(self, store: PersistentSessionStore) -> None:
        session = Session(id="load-me")
        store.save_session(session)
        loaded = store.load_session("load-me")
        assert loaded is not None
        assert loaded.id == "load-me"

    def test_load_nonexistent(self, store: PersistentSessionStore) -> None:
        loaded = store.load_session("nonexistent")
        assert loaded is None

    def test_load_all_sessions(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="a"))
        store.save_session(Session(id="b"))
        store.save_session(Session(id="c"))
        sessions = store.load_all_sessions()
        assert len(sessions) == 3

    def test_load_all_by_status(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="active-1", status="active"))
        store.save_session(Session(id="active-2", status="active"))
        store.save_session(Session(id="closed-1", status="closed"))
        active = store.load_all_sessions(status="active")
        closed = store.load_all_sessions(status="closed")
        assert len(active) == 2
        assert len(closed) == 1

    def test_load_all_empty(self, store: PersistentSessionStore) -> None:
        assert store.load_all_sessions() == []

    def test_load_all_by_nonexistent_status(self, store: PersistentSessionStore) -> None:
        assert store.load_all_sessions(status="nonexistent") == []


class TestPersistentSessionStoreDelete:
    def test_delete_existing(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="delete-me"))
        result = store.delete_session("delete-me")
        assert result is True
        assert store.load_session("delete-me") is None

    def test_delete_nonexistent(self, store: PersistentSessionStore) -> None:
        result = store.delete_session("ghost")
        assert result is False

    def test_delete_reduces_count(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="a"))
        store.save_session(Session(id="b"))
        store.delete_session("a")
        assert len(store.load_all_sessions()) == 1


class TestPersistentSessionStoreUpdateStatus:
    def test_update_status(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="status-test", status="active"))
        result = store.update_session_status("status-test", "closed")
        assert result is True
        loaded = store.load_session("status-test")
        assert loaded is not None
        assert loaded.status == "closed"

    def test_update_status_nonexistent(self, store: PersistentSessionStore) -> None:
        result = store.update_session_status("ghost", "closed")
        assert result is False


class TestPersistentSessionStoreHeartbeat:
    def test_update_heartbeat(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="hb-test"))
        old = store.load_session("hb-test")
        assert old is not None
        result = store.update_heartbeat("hb-test")
        assert result is True
        updated = store.load_session("hb-test")
        assert updated is not None
        assert updated.last_heartbeat >= old.last_heartbeat

    def test_update_heartbeat_nonexistent(self, store: PersistentSessionStore) -> None:
        result = store.update_heartbeat("ghost")
        assert result is False


class TestPersistentSessionStoreCountByStatus:
    def test_count_empty(self, store: PersistentSessionStore) -> None:
        assert store.count_by_status() == {}

    def test_count_by_status(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="a", status="active"))
        store.save_session(Session(id="b", status="active"))
        store.save_session(Session(id="c", status="closed"))
        counts = store.count_by_status()
        assert counts.get("active") == 2
        assert counts.get("closed") == 1

    def test_count_after_delete(self, store: PersistentSessionStore) -> None:
        store.save_session(Session(id="a", status="active"))
        store.save_session(Session(id="b", status="active"))
        store.delete_session("a")
        counts = store.count_by_status()
        assert counts.get("active") == 1


class TestPersistentSessionStoreCleanupExpired:
    def test_cleanup_no_expired(self, store: PersistentSessionStore) -> None:
        session = Session(id="fresh", ttl=3600.0)
        store.save_session(session)
        count = store.cleanup_expired()
        assert count == 0

    def test_cleanup_expired(self, store: PersistentSessionStore) -> None:
        session = Session(id="old", ttl=3600.0)
        session.last_heartbeat = "2020-01-01T00:00:00+00:00"
        store.save_session(session)
        count = store.cleanup_expired()
        assert count == 1
        loaded = store.load_session("old")
        assert loaded is not None
        assert loaded.status == "expired"

    def test_cleanup_expired_only_affects_expired(self, store: PersistentSessionStore) -> None:
        old = Session(id="old", ttl=3600.0)
        old.last_heartbeat = "2020-01-01T00:00:00+00:00"
        fresh = Session(id="fresh", ttl=3600.0)
        store.save_session(old)
        store.save_session(fresh)
        count = store.cleanup_expired()
        assert count == 1
        loaded_fresh = store.load_session("fresh")
        assert loaded_fresh is not None
        assert loaded_fresh.status == "active"


class TestPersistentSessionStoreEdgeCases:
    def test_large_metadata(self, store: PersistentSessionStore) -> None:
        large = {"data": "x" * 50000}
        store.save_session(Session(id="large", metadata=large))
        loaded = store.load_session("large")
        assert loaded is not None
        assert len(loaded.metadata["data"]) == 50000

    def test_many_task_ids(self, store: PersistentSessionStore) -> None:
        task_ids = [f"task-{i}" for i in range(500)]
        store.save_session(Session(id="many-tasks", task_ids=task_ids))
        loaded = store.load_session("many-tasks")
        assert loaded is not None
        assert len(loaded.task_ids) == 500

    def test_context_manager(self, db_path: Path) -> None:
        with PersistentSessionStore(db_path) as store:
            store.save_session(Session(id="ctx-test"))
        assert db_path.exists()
        with PersistentSessionStore(db_path) as store:
            loaded = store.load_session("ctx-test")
            assert loaded is not None
            assert loaded.id == "ctx-test"

    def test_session_roundtrip_all_fields(self, store: PersistentSessionStore) -> None:
        original = Session(
            id="full-test",
            status="active",
            ttl=1800.0,
            metadata={"key": "value", "nested": {"a": 1}},
            task_ids=["t1", "t2"],
            sandbox_id="sb-1",
        )
        store.save_session(original)
        loaded = store.load_session("full-test")
        assert loaded is not None
        assert loaded.id == original.id
        assert loaded.status == original.status
        assert loaded.ttl == original.ttl
        assert loaded.metadata == original.metadata
        assert loaded.task_ids == original.task_ids

    def test_json_serializable_via_sqlite(self, store: PersistentSessionStore) -> None:
        meta = {"unicode": "你好", "list": [1, 2, 3]}
        store.save_session(Session(id="unicode", metadata=meta))
        loaded = store.load_session("unicode")
        assert loaded is not None
        assert loaded.metadata == meta
