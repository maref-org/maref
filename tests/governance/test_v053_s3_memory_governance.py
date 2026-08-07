"""v0.53 S3: 记忆治理（deidentify / forget / erasure / retention）。

验证：
1. deidentify 后 agent_id 不可恢复且语义保留
2. forget 软删除：记录仍存在但标记 deleted
3. erasure 硬删除：记录不可恢复
4. retention 策略超期自动清理（分 tier）
"""

from __future__ import annotations

import time

from maref.governance.audit import AuditLogger
from maref.memory.memory_manager import (
    MemoryManager,
    MemoryRecord,
    MemoryRetentionPolicy,
    UserIsolationTag,
)


def _seed(mm: MemoryManager, agent: str = "agent-007") -> MemoryRecord:
    return mm.working.put(
        mm.create_record(
            content={"agent_id": agent, "task_type": "research", "text": "sensitive PII"},
            user_tag=UserIsolationTag(user_id=agent),
        )
    )


class TestDeidentify:
    def test_agent_id_replaced_irreversibly(self):
        mm = MemoryManager()
        rec = _seed(mm)
        assert rec.content["agent_id"] == "agent-007"

        count = mm.deidentify("agent-007")
        assert count == 1

        updated = mm.working.get(rec.memory_id)
        assert updated is not None
        assert updated.content["agent_id"] != "agent-007"
        assert not updated.content["agent_id"].startswith("agent-007")
        assert "sensitive PII" in str(updated.content)

    def test_isolation_tag_deidentified(self):
        mm = MemoryManager()
        rec = _seed(mm)
        mm.deidentify("agent-007")
        updated = mm.working.get(rec.memory_id)
        assert updated is not None
        assert updated.user_tag.user_id != "agent-007"

    def test_no_match_noop(self):
        mm = MemoryManager()
        _seed(mm, "agent-007")
        assert mm.deidentify("nonexistent-agent") == 0


class TestForgetAndErasure:
    def test_forget_soft_deletes(self):
        mm = MemoryManager()
        rec = _seed(mm)
        assert mm.forget(rec.memory_id) is True
        updated = mm.working.get(rec.memory_id)
        assert updated is not None
        assert updated.deleted is True
        assert mm.forget("missing") is False

    def test_erasure_hard_deletes(self):
        mm = MemoryManager()
        rec = _seed(mm)
        assert mm.erasure(rec.memory_id) is True
        assert mm.working.get(rec.memory_id) is None
        assert mm.erasure("missing") is False

    def test_erasure_across_all_tiers(self):
        mm = MemoryManager()
        rec = _seed(mm)
        mm.semantic.store(rec)
        assert mm.erasure(rec.memory_id) is True
        assert mm.working.get(rec.memory_id) is None
        assert mm.semantic.retrieve(rec.memory_id) is None


class TestRetention:
    def test_hot_retention_purges_expired(self):
        policy = MemoryRetentionPolicy(hot_max_age_seconds=10)
        mm = MemoryManager(retention_policy=policy)
        rec = _seed(mm)
        rec.created_at = time.time() - 100
        removed = mm.apply_retention()
        assert removed["working"] == 1
        assert mm.working.get(rec.memory_id) is None

    def test_warm_retention_purges_expired(self):
        policy = MemoryRetentionPolicy(warm_max_age_seconds=10)
        mm = MemoryManager(retention_policy=policy)
        rec = _seed(mm)
        rec.created_at = time.time() - 100
        mm.episodic.append(rec)
        removed = mm.apply_retention()
        assert removed["episodic"] == 1
        assert mm.episodic.query(
            __import__("maref.memory.memory_manager", fromlist=["MemoryQuery"]).MemoryQuery()
        ) == []

    def test_cold_retention_purges_expired(self):
        policy = MemoryRetentionPolicy(cold_max_age_seconds=10)
        mm = MemoryManager(retention_policy=policy)
        rec = _seed(mm)
        rec.created_at = time.time() - 100
        mm.semantic.store(rec)
        removed = mm.apply_retention()
        assert removed["semantic"] == 1
        assert mm.semantic.retrieve(rec.memory_id) is None

    def test_recent_records_kept(self):
        policy = MemoryRetentionPolicy(hot_max_age_seconds=3600)
        mm = MemoryManager(retention_policy=policy)
        _seed(mm)
        removed = mm.apply_retention()
        assert removed["working"] == 0
        assert len(mm.working) == 1

    def test_zero_bound_keeps_forever(self):
        mm = MemoryManager()  # default policy: all bounds 0
        rec = _seed(mm)
        rec.created_at = time.time() - 999999
        removed = mm.apply_retention()
        assert sum(removed.values()) == 0
        assert mm.working.get(rec.memory_id) is not None


class TestAuditTrail:
    def test_erasure_writes_audit(self, tmp_path):
        import os

        os.environ.setdefault("MAREF_HMAC_SECRET_KEY", "test-hmac-key")
        logger = AuditLogger(log_path=str(tmp_path / "audit.jsonl"))
        mm = MemoryManager(audit_logger=logger)
        rec = _seed(mm)
        mm.erasure(rec.memory_id)
        entries = logger.read_all()
        types = [e.event_type for e in entries]
        assert "memory.erasure" in types
