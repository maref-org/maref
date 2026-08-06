"""Tests for experience_pool.py — ExperiencePool, ContextManager."""
from __future__ import annotations

import time

import pytest

from maref.recursive.experience_pool import (
    ContextManager,
    ExperienceEntry,
    ExperiencePool,
    _compute_precondition_hash,
)


class TestComputePreconditionHash:
    def test_hash_consistency(self):
        assert _compute_precondition_hash("hello") == _compute_precondition_hash("hello")

    def test_hash_different(self):
        assert _compute_precondition_hash("hello") != _compute_precondition_hash("world")


class TestExperiencePool:
    def test_initial_state(self):
        pool = ExperiencePool()
        assert pool.count() == 0

    def test_store_and_count(self):
        pool = ExperiencePool()
        entry = ExperienceEntry(
            entry_id="e1", timestamp=time.time(), context="test",
            decision="approve", outcome="success", lesson_learned="works",
        )
        pool.store(entry)
        assert pool.count() == 1

    def test_store_triggers_max_entries(self):
        pool = ExperiencePool(max_entries=2)
        for i in range(5):
            pool.store(ExperienceEntry(
                entry_id=f"e{i}", timestamp=time.time(), context=f"ctx{i}",
                decision="d", outcome="success", lesson_learned="l",
            ))
        assert pool.count() == 2

    def test_on_store_callback(self):
        pool = ExperiencePool()
        callback_results = []

        def cb(entry):
            callback_results.append(entry.entry_id)

        pool.on_store(cb)
        pool.store(ExperienceEntry(
            entry_id="e1", timestamp=time.time(), context="test",
            decision="d", outcome="success", lesson_learned="l",
        ))
        assert callback_results == ["e1"]

    def test_query_by_tag(self):
        pool = ExperiencePool()
        entry = ExperienceEntry(
            entry_id="e1", timestamp=time.time(), context="test",
            decision="d", outcome="success", lesson_learned="l",
            tags=["critical", "bug"],
        )
        pool.store(entry)
        results = pool.query_by_tag("critical")
        assert len(results) == 1
        assert results[0].entry_id == "e1"
        assert pool.query_by_tag("nonexistent") == []

    def test_query_by_outcome(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "ctx", "d", "success", "l"))
        pool.store(ExperienceEntry("e2", time.time(), "ctx", "d", "failure", "l"))
        assert len(pool.query_by_outcome("success")) == 1
        assert len(pool.query_by_outcome("failure")) == 1
        assert pool.query_by_outcome("unknown") == []

    def test_query_by_context(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "database timeout", "d", "failure", "l"))
        pool.store(ExperienceEntry("e2", time.time(), "network error", "d", "failure", "l"))
        assert len(pool.query_by_context("database")) == 1
        assert len(pool.query_by_context("error")) == 1
        assert pool.query_by_context("nonexistent") == []

    def test_search_similar(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "database connection failed", "d", "failure", "l1"))
        pool.store(ExperienceEntry("e2", time.time(), "network timeout", "d", "failure", "l2"))
        results = pool.search_similar("database", max_results=5)
        assert len(results) >= 1
        assert results[0].entry_id == "e1"

    def test_search_similar_empty(self):
        pool = ExperiencePool()
        assert pool.search_similar("anything") == []

    def test_replay_lessons(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "ctx", "d", "failure", "lesson 1"))
        pool.store(ExperienceEntry("e2", time.time(), "ctx", "d", "success", "lesson 2"))
        lessons = pool.replay_lessons("failure")
        assert lessons == ["lesson 1"]

    def test_search_similar_with_decay(self):
        pool = ExperiencePool()
        entry = ExperienceEntry(
            "e1", time.time(), "database error", "d", "failure",
            "lesson", version_tag="v1",
        )
        pool.store(entry)
        results = pool.search_similar_with_decay("database error", current_version="v1")
        assert len(results) == 1

    def test_search_similar_with_decay_no_match(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "aaa bbb", "d", "success", "l"))
        assert pool.search_similar_with_decay("ccc ddd") == []

    def test_purge_stale(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time() - 1_000_000, "old", "d", "success", "l"))
        pool.store(ExperienceEntry("e2", time.time(), "new", "d", "success", "l"))
        removed = pool.purge_stale(max_age_hours=1)
        assert removed >= 1

    def test_clear(self):
        pool = ExperiencePool()
        pool.store(ExperienceEntry("e1", time.time(), "ctx", "d", "success", "l"))
        pool.clear()
        assert pool.count() == 0


class TestContextManager:
    def test_initial_state(self):
        cm = ContextManager()
        assert cm.session_count() == 0
        assert cm.get_active_context() is None

    def test_start_session(self):
        cm = ContextManager()
        cm.start_session("session-1")
        assert cm.session_count() == 1
        active = cm.get_active_context()
        assert active is not None
        assert active["session_id"] == "session-1"

    def test_push_context(self):
        cm = ContextManager()
        cm.start_session("session-1")
        cm.push_context("key1", "value1")
        active = cm.get_active_context()
        assert len(active["context_stack"]) == 1

    def test_push_context_no_active_session(self):
        cm = ContextManager()
        cm.push_context("key1", "value1")  # should not raise

    def test_pop_context(self):
        cm = ContextManager()
        cm.start_session("session-1")
        cm.push_context("key1", "value1")
        popped = cm.pop_context()
        assert popped is not None
        assert popped["key"] == "key1"
        assert cm.pop_context() is None

    def test_pop_context_no_active_session(self):
        cm = ContextManager()
        assert cm.pop_context() is None

    def test_record_decision(self):
        cm = ContextManager()
        cm.start_session("session-1")
        cm.record_decision("decision-1")
        active = cm.get_active_context()
        assert active["decision_count"] == 1

    def test_record_decision_no_active_session(self):
        cm = ContextManager()
        cm.record_decision("d1")  # should not raise

    def test_end_session(self):
        cm = ContextManager()
        cm.start_session("session-1")
        cm.record_decision("d1")
        session = cm.end_session()
        assert session is not None
        assert session["session_id"] == "session-1"
        assert cm.get_active_context() is None

    def test_end_session_no_active(self):
        cm = ContextManager()
        assert cm.end_session() is None

    def test_max_sessions(self):
        cm = ContextManager(max_sessions=2)
        for i in range(5):
            cm.start_session(f"session-{i}")
        # last session becomes active
        cm.end_session()
        assert cm.session_count() <= 2

    def test_find_session(self):
        cm = ContextManager()
        cm.start_session("s1")
        assert cm._find_session("s1") is not None
        assert cm._find_session("nonexistent") is None
