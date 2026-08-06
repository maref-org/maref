"""Tests for MemoryManager and three-tier memory architecture."""

import time

from maref.memory.memory_manager import (
    ConfidenceLabel,
    EpisodicMemoryStore,
    MemoryManager,
    MemoryQuery,
    MemoryRecord,
    SemanticMemoryStore,
    SourceAnnotation,
    UserIsolationTag,
    WorkingMemoryStore,
)


class TestUserIsolationTag:
    def test_shared_tag_matches_all(self):
        shared = UserIsolationTag()
        private = UserIsolationTag("user1", "sess1")
        assert shared.matches(private)
        assert private.matches(shared)

    def test_same_user_matches(self):
        a = UserIsolationTag("user1", "sess1")
        b = UserIsolationTag("user1", "sess2")
        assert a.matches(b)

    def test_different_user_no_match(self):
        a = UserIsolationTag("user1")
        b = UserIsolationTag("user2")
        assert not a.matches(b)


class TestMemoryRecord:
    def test_touch_updates_access(self):
        r = MemoryRecord(content={"key": "val"})
        assert r.access_count == 0
        r.touch()
        assert r.access_count == 1
        assert r.last_accessed_at > r.created_at

    def test_expiration(self):
        r = MemoryRecord(content={})
        r.expires_at = time.time() - 1
        assert r.is_expired()

    def test_no_expiration(self):
        r = MemoryRecord(content={})
        r.expires_at = 0
        assert not r.is_expired()


class TestWorkingMemoryStore:
    def test_put_and_get(self):
        store = WorkingMemoryStore(ttl_seconds=60)
        r = MemoryRecord(memory_id="m1", content={"state": "running"})
        store.put(r)
        got = store.get("m1")
        assert got is not None
        assert got.content["state"] == "running"

    def test_expired_record_removed(self):
        store = WorkingMemoryStore(ttl_seconds=0.01)
        r = MemoryRecord(memory_id="m1", content={})
        store.put(r)
        time.sleep(0.02)
        assert store.get("m1") is None

    def test_query_by_keywords(self):
        store = WorkingMemoryStore(ttl_seconds=60)
        store.put(MemoryRecord(memory_id="m1", content={"msg": "hello world"}))
        store.put(MemoryRecord(memory_id="m2", content={"msg": "goodbye"}))
        results = store.query(MemoryQuery(keywords=["hello"]))
        assert len(results) == 1
        assert results[0].memory_id == "m1"

    def test_query_user_isolation(self):
        store = WorkingMemoryStore(ttl_seconds=60)
        store.put(
            MemoryRecord(
                memory_id="m1",
                content={},
                user_tag=UserIsolationTag("user1", "sess1"),
            )
        )
        store.put(
            MemoryRecord(
                memory_id="m2",
                content={},
                user_tag=UserIsolationTag("user2", "sess2"),
            )
        )
        results = store.query(MemoryQuery(user_tag=UserIsolationTag("user1")))
        assert len(results) == 1
        assert results[0].memory_id == "m1"

    def test_checkpoint_and_restore(self):
        store = WorkingMemoryStore(ttl_seconds=60)
        store.put(MemoryRecord(memory_id="m1", content={"k": "v"}))
        cp = store.checkpoint()
        store2 = WorkingMemoryStore()
        store2.restore(cp)
        assert store2.get("m1") is not None
        assert store2.get("m1").content["k"] == "v"

    def test_pub_sub(self):
        store = WorkingMemoryStore(ttl_seconds=60)
        events: list[tuple[str, str]] = []
        store.subscribe(lambda ev, rec: events.append((ev, rec.memory_id)))
        store.put(MemoryRecord(memory_id="m1", content={}))
        assert ("put", "m1") in events

    def test_clear_expired(self):
        store = WorkingMemoryStore(ttl_seconds=0.01)
        store.put(MemoryRecord(memory_id="m1", content={}))
        time.sleep(0.02)
        cleared = store.clear_expired()
        assert cleared == 1
        assert len(store) == 0


class TestEpisodicMemoryStore:
    def test_append_and_query(self):
        store = EpisodicMemoryStore()
        store.append(MemoryRecord(memory_id="e1", content={"task_type": "analysis"}))
        results = store.query(MemoryQuery(keywords=["analysis"]))
        assert len(results) == 1

    def test_get_agent_history(self):
        store = EpisodicMemoryStore()
        store.append(
            MemoryRecord(
                memory_id="e1",
                content={"agent_id": "agent-a", "outcome": "success"},
            )
        )
        store.append(
            MemoryRecord(
                memory_id="e2",
                content={"agent_id": "agent-b", "outcome": "failure"},
            )
        )
        history = store.get_agent_history("agent-a")
        assert len(history) == 1
        assert history[0].memory_id == "e1"

    def test_summarize_episodes(self):
        store = EpisodicMemoryStore()
        for i in range(5):
            store.append(
                MemoryRecord(
                    content={"task_type": "report", "outcome": "success", "duration_ms": 100},
                )
            )
        store.append(
            MemoryRecord(
                content={"task_type": "report", "outcome": "failure", "duration_ms": 200},
            )
        )
        summary = store.summarize_episodes("report")
        assert summary["count"] == 6
        assert summary["success_rate"] == 5 / 6

    def test_archive_old(self):
        store = EpisodicMemoryStore()
        old = MemoryRecord(content={"old": True})
        old.created_at = time.time() - 100 * 86400
        store.append(old)
        store.append(MemoryRecord(content={"new": True}))
        archived = store.archive_old(max_age_days=90)
        assert len(archived) == 1
        assert len(store) == 1


class TestSemanticMemoryStore:
    def test_store_and_retrieve(self):
        store = SemanticMemoryStore()
        r = MemoryRecord(memory_id="s1", content={"concept": "pricing", "fact": "base=$10"})
        store.store(r)
        got = store.retrieve("s1")
        assert got is not None
        assert got.content["concept"] == "pricing"

    def test_query_keywords(self):
        store = SemanticMemoryStore()
        store.store(MemoryRecord(content={"text": "machine learning is powerful"}))
        store.store(MemoryRecord(content={"text": "deep learning subset of ml"}))
        results = store.query(MemoryQuery(keywords=["machine", "learning"]))
        assert len(results) == 2

    def test_get_ontology(self):
        store = SemanticMemoryStore()
        store.store(MemoryRecord(content={"concept": "agent", "def": "autonomous entity"}))
        store.store(MemoryRecord(content={"concept": "agent", "def": "software agent"}))
        store.store(MemoryRecord(content={"concept": "tool", "def": "instrument"}))
        results = store.get_ontology("agent")
        assert len(results) == 2


class TestMemoryManager:
    def test_create_record(self):
        mm = MemoryManager()
        r = mm.create_record(
            content={"key": "val"},
            confidence=ConfidenceLabel.HIGH,
            source=SourceAnnotation.HUMAN,
        )
        assert r.confidence == ConfidenceLabel.HIGH
        assert r.source == SourceAnnotation.HUMAN

    def test_query_all_tiers(self):
        mm = MemoryManager()
        mm.working.put(MemoryRecord(content={"tier": "hot", "data": "runtime"}))
        mm.episodic.append(MemoryRecord(content={"tier": "warm", "data": "history"}))
        mm.semantic.store(MemoryRecord(content={"tier": "cold", "data": "knowledge"}))
        results = mm.query_all_tiers(MemoryQuery())
        assert len(results["working"]) == 1
        assert len(results["episodic"]) == 1
        # Semantic requires keywords to match; query with empty keywords returns all
        results_semantic = mm.semantic.query(MemoryQuery(keywords=["knowledge"]))
        assert len(results_semantic) == 1

    def test_decay_and_archive(self):
        mm = MemoryManager()
        old = MemoryRecord(content={"old": True})
        old.created_at = time.time() - 100 * 86400
        mm.episodic.append(old)
        stats = mm.decay_and_archive()
        assert stats["episodic_archived"] == 1
        assert len(mm.semantic) == 1

    def test_stats(self):
        mm = MemoryManager()
        mm.working.put(MemoryRecord(content={}))
        mm.episodic.append(MemoryRecord(content={}))
        mm.semantic.store(MemoryRecord(content={}))
        stats = mm.get_stats()
        assert stats["working_count"] == 1
        assert stats["episodic_count"] == 1
        assert stats["semantic_count"] == 1
