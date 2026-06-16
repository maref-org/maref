from __future__ import annotations

import time

from maref.recursive.experience_pool import (
    ExperienceEntry,
    ExperiencePool,
    _compute_precondition_hash,
)


class TestExperienceEntryDecay:
    def test_default_version_tag(self) -> None:
        e = ExperienceEntry(
            entry_id="e1",
            timestamp=time.time(),
            context="test context",
            decision="do_x",
            outcome="success",
            lesson_learned="keep doing x",
            tags=["t1"],
        )
        assert e.version_tag == "unknown"
        assert e.precondition_hash is None
        assert e.decay_factor == 1.0

    def test_version_tag_explicit(self) -> None:
        e = ExperienceEntry(
            entry_id="e1",
            timestamp=time.time(),
            context="test context",
            decision="do_x",
            outcome="success",
            lesson_learned="keep doing x",
            version_tag="v0.5.0-r22",
            precondition_hash="abc123",
            decay_factor=0.5,
        )
        assert e.version_tag == "v0.5.0-r22"
        assert e.precondition_hash == "abc123"
        assert e.decay_factor == 0.5

    def test_precondition_hash_computation(self) -> None:
        h = _compute_precondition_hash("some context")
        assert len(h) == 16
        assert _compute_precondition_hash("some context") == h
        assert _compute_precondition_hash("different") != h


class TestSearchSimilarWithDecay:
    def _make_entry(
        self,
        entry_id: str,
        context: str,
        version_tag: str = "v0.5.0",
        age_hours: float = 0.0,
        decay_factor: float = 1.0,
    ) -> ExperienceEntry:
        return ExperienceEntry(
            entry_id=entry_id,
            timestamp=time.time() - age_hours * 3600,
            context=context,
            decision="d",
            outcome="success",
            lesson_learned="ll",
            version_tag=version_tag,
            decay_factor=decay_factor,
        )

    def test_version_match_boosts_score(self) -> None:
        pool = ExperiencePool()
        e1 = self._make_entry("e1", "test module coverage", version_tag="v0.5.0")
        e2 = self._make_entry("e2", "test module checker", version_tag="v0.3.0")
        pool.store(e1)
        pool.store(e2)
        results = pool.search_similar_with_decay("test module", current_version="v0.5.0")
        assert len(results) == 2
        assert results[0].entry_id == "e1"

    def test_older_entries_decay(self) -> None:
        pool = ExperiencePool()
        e1 = self._make_entry("e1", "test module", age_hours=0)
        e2 = self._make_entry("e2", "test module", age_hours=48)
        pool.store(e1)
        pool.store(e2)
        results = pool.search_similar_with_decay("test module", current_version="v0.5.0")
        assert results[0].entry_id == "e1"

    def test_decay_factor_multiplies_score(self) -> None:
        pool = ExperiencePool()
        e1 = self._make_entry("e1", "test module", decay_factor=1.0)
        e2 = self._make_entry("e2", "test module", decay_factor=0.1)
        pool.store(e1)
        pool.store(e2)
        results = pool.search_similar_with_decay("test module")
        assert results[0].entry_id == "e1"

    def test_no_overlap_returns_empty(self) -> None:
        pool = ExperiencePool()
        pool.store(self._make_entry("e1", "foo bar"))
        results = pool.search_similar_with_decay("xyz abc")
        assert results == []

    def test_max_results(self) -> None:
        pool = ExperiencePool()
        for i in range(10):
            pool.store(self._make_entry(f"e{i}", "test module"))
        results = pool.search_similar_with_decay("test module", max_results=3)
        assert len(results) == 3

    def test_no_current_version(self) -> None:
        pool = ExperiencePool()
        e1 = self._make_entry("e1", "test module", version_tag="v0.5.0")
        e2 = self._make_entry("e2", "test module", version_tag="v0.3.0")
        pool.store(e1)
        pool.store(e2)
        results = pool.search_similar_with_decay("test module")
        assert len(results) == 2


class TestPurgeStale:
    def _make_entry(self, entry_id: str, age_hours: float) -> ExperienceEntry:
        return ExperienceEntry(
            entry_id=entry_id,
            timestamp=time.time() - age_hours * 3600,
            context="c",
            decision="d",
            outcome="success",
            lesson_learned="ll",
        )

    def test_purge_stale_removes_old_entries(self) -> None:
        pool = ExperiencePool()
        pool.store(self._make_entry("e1", 0))
        pool.store(self._make_entry("e2", 800))
        removed = pool.purge_stale(max_age_hours=720)
        assert removed == 1
        assert pool.count() == 1

    def test_purge_stale_keeps_recent(self) -> None:
        pool = ExperiencePool()
        pool.store(self._make_entry("e1", 0))
        pool.store(self._make_entry("e2", 10))
        removed = pool.purge_stale(max_age_hours=24)
        assert removed == 0
        assert pool.count() == 2

    def test_purge_stale_empty_pool(self) -> None:
        pool = ExperiencePool()
        removed = pool.purge_stale()
        assert removed == 0
