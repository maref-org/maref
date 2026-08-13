from __future__ import annotations

from maref.immunity.cooldown_manager import CooldownManager
from maref.immunity.cross_gen_simulator import CrossGenerationImpactSimulator
from maref.recursive.unified_audit import UnifiedAuditStore

CLEAN_CODE = """
def add(a, b):
    return a + b
"""

CONTAMINATED_CODE = """
import pickle

def save(data):
    pickle.dump(data, f)

# Production-grade secure implementation
result = eval(user_input)
"""


class TestCooldownManagerSubmit:
    """5.2-A1: code_merged → cooldown_24h state."""

    def test_submit_code_returns_cooldown_id(self):
        manager = CooldownManager()
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        assert cid.startswith("cd_")

    def test_submit_code_status_cooling(self):
        manager = CooldownManager()
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        status = manager.get_status(cid)
        assert status["status"] == "cooling"

    def test_submit_code_not_merged(self):
        manager = CooldownManager()
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        status = manager.get_status(cid)
        assert status["merged"] is False

    def test_default_cooldown_is_24h(self):
        manager = CooldownManager()
        assert manager.get_cooldown_seconds() == 86400.0

    def test_custom_cooldown(self):
        manager = CooldownManager(cooldown_seconds=3600.0)
        assert manager.get_cooldown_seconds() == 3600.0

    def test_get_all_entries(self):
        manager = CooldownManager()
        manager.submit_code("a", CLEAN_CODE)
        manager.submit_code("b", CLEAN_CODE)
        assert len(manager.get_all_entries()) == 2

    def test_get_status_unknown(self):
        manager = CooldownManager()
        status = manager.get_status("nonexistent")
        assert "error" in status


class TestCooldownManagerEvaluation:
    """5.2-A2: cooldown期间 cross_gen_simulator自动运行."""

    def test_evaluate_clean_code_not_blocked(self):
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        result = manager.evaluate(cid)
        assert result["blocked"] is False

    def test_evaluate_contaminated_code_blocked(self):
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim)
        cid = manager.submit_code("agent_a", CONTAMINATED_CODE)
        result = manager.evaluate(cid)
        assert result["blocked"] is True

    def test_evaluate_contaminated_high_index(self):
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim)
        cid = manager.submit_code("agent_a", CONTAMINATED_CODE)
        result = manager.evaluate(cid)
        assert result["contamination_index"] >= 0.7

    def test_evaluate_without_simulator_returns_error(self):
        manager = CooldownManager()
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        result = manager.evaluate(cid)
        assert "error" in result

    def test_evaluate_unknown_id(self):
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim)
        result = manager.evaluate("nonexistent")
        assert "error" in result


class TestCooldownManagerAutoMerge:
    """5.2-A3: contamination_index ≥ 0.7 → merge_blocked."""

    def test_auto_merge_clean_code_after_cooldown(self):
        manager = CooldownManager(cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        result = manager.auto_merge(cid)
        assert result["success"] is True

    def test_auto_merge_before_cooldown(self):
        manager = CooldownManager(cooldown_seconds=86400.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        result = manager.auto_merge(cid)
        assert result["success"] is False

    def test_auto_merge_blocked_code(self):
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CONTAMINATED_CODE)
        manager.evaluate(cid)
        result = manager.auto_merge(cid)
        assert result["success"] is False
        assert "blocked" in result["reason"]

    def test_auto_merge_sets_merged_flag(self):
        manager = CooldownManager(cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.auto_merge(cid)
        status = manager.get_status(cid)
        assert status["merged"] is True

    def test_auto_merge_status_merged(self):
        manager = CooldownManager(cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.auto_merge(cid)
        status = manager.get_status(cid)
        assert status["status"] == "merged"


class TestCooldownManagerForceMerge:
    """5.2-A3 (bypass): force_merge bypasses block."""

    def test_force_merge_blocked_code(self):
        sim = CrossGenerationImpactSimulator()
        store = UnifiedAuditStore()
        manager = CooldownManager(simulator=sim, audit_store=store, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CONTAMINATED_CODE)
        manager.evaluate(cid)
        result = manager.force_merge(cid, actor_id="test_operator")
        assert result["success"] is True

    def test_force_merge_unknown_id(self):
        manager = CooldownManager()
        result = manager.force_merge("nonexistent", actor_id="test_operator")
        assert result["success"] is False

    def test_force_merge_sets_force_merged_flag(self):
        store = UnifiedAuditStore()
        manager = CooldownManager(audit_store=store, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.force_merge(cid, actor_id="test_operator")
        status = manager.get_status(cid)
        assert status["force_merged"] is True

    def test_force_merge_status(self):
        store = UnifiedAuditStore()
        manager = CooldownManager(audit_store=store, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.force_merge(cid, actor_id="test_operator")
        status = manager.get_status(cid)
        assert status["status"] == "force_merged"


class TestCooldownManagerAudit:
    """5.2-A4: Events recorded in audit."""

    def test_submit_writes_audit(self):
        store = UnifiedAuditStore()
        manager = CooldownManager(audit_store=store)
        manager.submit_code("agent_a", CLEAN_CODE)
        assert store.count() >= 1

    def test_evaluate_writes_audit(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator()
        manager = CooldownManager(simulator=sim, audit_store=store)
        cid = manager.submit_code("agent_a", CONTAMINATED_CODE)
        manager.evaluate(cid)
        assert store.count() >= 2

    def test_auto_merge_writes_audit(self):
        store = UnifiedAuditStore()
        manager = CooldownManager(audit_store=store, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.auto_merge(cid)
        events = store.stats_by_event_type()
        assert any("merge" in k for k in events)

    def test_force_merge_writes_audit(self):
        store = UnifiedAuditStore()
        manager = CooldownManager(audit_store=store, cooldown_seconds=0.0)
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        manager.force_merge(cid, actor_id="test_operator")
        events = store.stats_by_event_type()
        assert any("force" in k for k in events)

    def test_no_audit_store_no_error(self):
        manager = CooldownManager()
        cid = manager.submit_code("agent_a", CLEAN_CODE)
        assert cid is not None
