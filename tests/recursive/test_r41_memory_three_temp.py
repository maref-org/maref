from __future__ import annotations

from maref.recursive.memory_three_temperature import (
    MemoryHealthScore,
    MemoryRecord,
    MemoryTemperature,
    MemoryThreeTemperature,
    TemperatureThresholds,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestMemoryTemperature:
    def test_all_temps(self) -> None:
        assert MemoryTemperature.HOT.value == "hot"
        assert MemoryTemperature.WARM.value == "warm"
        assert MemoryTemperature.COLD.value == "cold"
        assert MemoryTemperature.FROZEN.value == "frozen"


class TestMemoryRecord:
    def test_create(self) -> None:
        record = MemoryRecord(memory_id="m1")
        assert record.memory_id == "m1"
        assert record.temperature == MemoryTemperature.WARM
        assert record.access_count == 0

    def test_success_rate_zero_access(self) -> None:
        record = MemoryRecord(memory_id="m1")
        assert record.success_rate == 0.0

    def test_success_rate_calculated(self) -> None:
        record = MemoryRecord(memory_id="m1", access_count=10, success_count=8)
        assert record.success_rate == 0.8


class TestTemperatureThresholds:
    def test_defaults(self) -> None:
        t = TemperatureThresholds()
        assert t.hot_min_health == 0.75
        assert t.warm_min_health == 0.40
        assert t.alpha + t.beta + t.gamma == 1.0


class TestMemoryHealthScore:
    def test_create(self) -> None:
        score = MemoryHealthScore(
            memory_id="m1",
            temperature=MemoryTemperature.WARM,
            recency_score=0.6,
            frequency_score=0.5,
            relevance_score=0.8,
            impact_score=0.4,
            overall_health=0.575,
        )
        assert score.memory_id == "m1"
        d = score.to_dict()
        assert d["temperature"] == "warm"


class TestMemoryThreeTemperature:
    def setup_method(self) -> None:
        self.m3t = MemoryThreeTemperature()

    def test_store_default_warm(self) -> None:
        record = self.m3t.store("m1", {"data": "test"})
        assert record.temperature == MemoryTemperature.WARM
        assert self.m3t.get_memory("m1") is not None

    def test_store_specific_temp(self) -> None:
        record = self.m3t.store("m2", {"data": "hot_data"},
                                 initial_temp=MemoryTemperature.HOT)
        assert record.temperature == MemoryTemperature.HOT

    def test_access_increments_counter(self) -> None:
        self.m3t.store("m3", {"data": "x"})
        record = self.m3t.access("m3")
        assert record is not None
        assert record.access_count == 1

    def test_access_not_found(self) -> None:
        assert self.m3t.access("nonexistent") is None

    def test_score_health(self) -> None:
        self.m3t.store("m4", {"data": "healthy"})
        score = self.m3t.score_health("m4")
        assert score is not None
        assert 0.0 <= score.overall_health <= 1.0

    def test_promote_warm_to_hot(self) -> None:
        self.m3t.store("m5", {"data": "promotable"})
        record = self.m3t.get_memory("m5")
        assert record is not None
        record.access_count = 100
        record.success_count = 100
        record.last_accessed_at = record.created_at
        transition = self.m3t.promote("m5")
        assert transition is not None
        assert transition.to_temp == MemoryTemperature.HOT

    def test_demote_warm_to_cold(self) -> None:
        self.m3t.store("m6", {"data": "declining"})
        record = self.m3t.get_memory("m6")
        assert record is not None
        record.last_accessed_at = 0.0
        transition = self.m3t.demote("m6")
        assert transition is not None
        assert transition.to_temp == MemoryTemperature.COLD

    def test_auto_balance(self) -> None:
        self.m3t.store("m7", {"data": "hot"}, initial_temp=MemoryTemperature.HOT)
        self.m3t.store("m8", {"data": "cold"}, initial_temp=MemoryTemperature.COLD)
        transitions = self.m3t.auto_balance()
        assert isinstance(transitions, list)

    def test_get_by_temperature(self) -> None:
        self.m3t.store("h1", {}, MemoryTemperature.HOT)
        self.m3t.store("w1", {}, MemoryTemperature.WARM)
        hots = self.m3t.get_by_temperature(MemoryTemperature.HOT)
        assert len(hots) == 1
        warms = self.m3t.get_by_temperature(MemoryTemperature.WARM)
        assert len(warms) == 1

    def test_query_by_relevance(self) -> None:
        self.m3t.store("doc1", {"text": "python async coroutine"})
        self.m3t.store("doc2", {"text": "rust borrow checker lifetime"})
        results = self.m3t.query_by_relevance(["python", "async"], limit=5)
        assert len(results) >= 1
        assert "python" in str(results[0].content).lower()

    def test_get_stats(self) -> None:
        self.m3t.store("s1", {}, MemoryTemperature.HOT)
        self.m3t.store("s2", {}, MemoryTemperature.WARM)
        self.m3t.store("s3", {}, MemoryTemperature.COLD)
        stats = self.m3t.get_stats()
        assert stats["total_memories"] == 3
        assert stats["hot_count"] == 1
        assert stats["warm_count"] == 1
        assert stats["cold_count"] == 1

    def test_capacity_enforcement(self) -> None:
        m3t = MemoryThreeTemperature(
            thresholds=TemperatureThresholds(max_hot_count=2),
        )
        m3t.store("h1", {}, MemoryTemperature.HOT)
        m3t.store("h2", {}, MemoryTemperature.HOT)
        m3t.store("h3", {}, MemoryTemperature.HOT)
        m3t.auto_balance()
        assert m3t.get_stats()["hot_count"] <= 2

    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        m3t = MemoryThreeTemperature(audit_store=audit)
        m3t.store("a1", {})
        assert audit.count() >= 0

    def test_clear(self) -> None:
        self.m3t.store("c1", {})
        self.m3t.clear()
        assert self.m3t.get_stats()["total_memories"] == 0

    def test_frozen_temperature(self) -> None:
        self.m3t.store("f1", {}, MemoryTemperature.FROZEN)
        record = self.m3t.get_memory("f1")
        assert record is not None
        assert record.temperature == MemoryTemperature.FROZEN

    def test_promote_nonexistent(self) -> None:
        assert self.m3t.promote("no_such") is None

    def test_demote_nonexistent(self) -> None:
        assert self.m3t.demote("no_such") is None

    def test_score_health_nonexistent(self) -> None:
        assert self.m3t.score_health("no_such") is None

    def test_query_by_relevance_empty(self) -> None:
        results = self.m3t.query_by_relevance([], limit=5)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_access_updates_timestamp(self) -> None:
        self.m3t.store("ts1", {})
        import time
        before = time.time()
        record = self.m3t.access("ts1")
        assert record is not None
        assert record.last_accessed_at >= before

    def test_get_by_temperature_frozen(self) -> None:
        self.m3t.store("fr1", {}, MemoryTemperature.FROZEN)
        frozen = self.m3t.get_by_temperature(MemoryTemperature.FROZEN)
        assert len(frozen) == 1

    def test_auto_balance_empty(self) -> None:
        m3t = MemoryThreeTemperature()
        transitions = m3t.auto_balance()
        assert transitions == []

    def test_promote_already_hot(self) -> None:
        self.m3t.store("hot1", {}, MemoryTemperature.HOT)
        record = self.m3t.get_memory("hot1")
        assert record is not None
        record.access_count = 200
        record.success_count = 200
        record.last_accessed_at = record.created_at
        transition = self.m3t.promote("hot1")
        assert transition is None

    def test_demote_already_frozen(self) -> None:
        self.m3t.store("frz1", {}, MemoryTemperature.FROZEN)
        record = self.m3t.get_memory("frz1")
        assert record is not None
        record.last_accessed_at = 0.0
        transition = self.m3t.demote("frz1")
        assert transition is None

    def test_capacity_cold_enforcement(self) -> None:
        m3t = MemoryThreeTemperature(
            thresholds=TemperatureThresholds(max_cold_count=1),
        )
        m3t.store("c1", {}, MemoryTemperature.COLD)
        m3t.store("c2", {}, MemoryTemperature.COLD)
        m3t.auto_balance()
        assert m3t.get_stats()["cold_count"] <= 1
