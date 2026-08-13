"""v0.53 S3 — 记忆治理（去识别/保留期/遗忘权）验收测试。

对齐缺口: 25-MAREF-治理三维度缺口审计报告-20260805 S3（P1-1）
跨会话记忆无去识别/保留期/遗忘权 → 不满足个保法 / AI Act。
本套件验证: PII 检测与脱敏、字段键识别、保留期到期清理、GDPR Art17 遗忘权擦除、治理事件 hook。
"""

from __future__ import annotations

import time

from maref.memory.memory_manager import (
    MemoryManager,
    MemoryRecord,
    PiiCategory,
    UserIsolationTag,
    deidentify_content,
    detect_pii,
)


class TestDetectPii:
    def test_email_phone_id_card(self) -> None:
        hits = detect_pii(
            {
                "contact": "email: alice@example.com, phone: 13812345678",
                "note": "id 110101199001011234",
            }
        )
        assert PiiCategory.EMAIL in hits
        assert PiiCategory.PHONE in hits
        assert PiiCategory.ID_CARD in hits
        assert "alice@example.com" in hits[PiiCategory.EMAIL]

    def test_phone_with_intl_prefix_and_separators(self) -> None:
        hits = detect_pii(
            {
                "a": "call +86 138-1234-5678 now",
                "b": "alt 138 1234 5678",
            }
        )
        assert PiiCategory.PHONE in hits
        assert "+86 138-1234-5678" in hits[PiiCategory.PHONE]
        assert "138 1234 5678" in hits[PiiCategory.PHONE]

    def test_ssn_format(self) -> None:
        hits = detect_pii({"id": "ssn 123-45-6789"})
        assert PiiCategory.SSN in hits
        assert "123-45-6789" in hits[PiiCategory.SSN]

    def test_keyword_field_key_alias(self) -> None:
        hits = detect_pii({"email_address": "a@b.com", "phone_number": "13812345678"})
        assert PiiCategory.EMAIL in hits
        assert PiiCategory.PHONE in hits

    def test_non_string_key_no_crash(self) -> None:
        hits = detect_pii({1: "普通文本无敏感信息", "用户信息": "alice@example.com"})
        assert PiiCategory.EMAIL in hits
        assert len(hits) == 1

    def test_credit_card_and_ip(self) -> None:
        hits = detect_pii(
            {
                "payment": "card 4111-1111-1111-1111",
                "from": "192.168.1.10",
            }
        )
        assert PiiCategory.CREDIT_CARD in hits
        assert PiiCategory.IP_ADDRESS in hits

    def test_clean_content_no_hits(self) -> None:
        hits = detect_pii({"msg": "plain text without pii"})
        assert hits == {}


class TestDeidentifyContent:
    def test_masks_and_reports_categories(self) -> None:
        content = {
            "user": {"email": "alice@example.com", "phone": "13812345678"},
            "note": "talk to bob@corp.com",
        }
        out, cats = deidentify_content(content)
        assert PiiCategory.EMAIL in cats
        assert PiiCategory.PHONE in cats
        assert "alice@example.com" not in str(out)
        assert "bob@corp.com" not in str(out)
        assert "13812345678" not in str(out)

    def test_does_not_mutate_input(self) -> None:
        content = {"email": "alice@example.com"}
        out, _ = deidentify_content(content)
        assert content["email"] == "alice@example.com"
        assert out["email"] != content["email"]

    def test_field_key_scan_masks_name(self) -> None:
        out, cats = deidentify_content({"full_name": "Zhang San"})
        assert PiiCategory.NAME in cats
        assert "Zhang San" not in str(out)

    def test_field_key_fallback_masks_value_without_pattern_hit(self) -> None:
        """字段键命中的值不含对应 pattern 时，整个值按类别掩码兜底。"""
        out, cats = deidentify_content({"card_number": "none"})
        assert PiiCategory.CREDIT_CARD in cats
        assert "none" not in str(out)


class TestRecordRetention:
    def test_retention_days_default_zero(self) -> None:
        r = MemoryRecord(content={})
        assert r.retention_days == 0
        assert r.pii_categories == []


class TestStoreGovernance:
    def test_working_deidentify(self) -> None:
        mm = MemoryManager()
        mm.working.put(
            MemoryRecord(memory_id="m1", content={"email": "alice@example.com"})
        )
        assert mm.working.deidentify("m1")
        rec = mm.working.get("m1")
        assert rec is not None
        assert PiiCategory.EMAIL.value in rec.pii_categories
        assert "alice@example.com" not in str(rec.content)

    def test_working_erase_by_user(self) -> None:
        mm = MemoryManager()
        mm.working.put(
            MemoryRecord(memory_id="u1", content={}, user_tag=UserIsolationTag("u1"))
        )
        mm.working.put(
            MemoryRecord(memory_id="u2", content={}, user_tag=UserIsolationTag("u2"))
        )
        assert mm.working.erase_by_user("u1") == 1
        assert len(mm.working) == 1

    def test_working_purge_expired_retention(self) -> None:
        mm = MemoryManager()
        old = MemoryRecord(memory_id="old", content={})
        old.created_at = time.time() - 100 * 86400
        old.last_accessed_at = time.time() - 100 * 86400
        old.retention_days = 30
        mm.working.put(old)
        mm.working.put(MemoryRecord(memory_id="fresh", content={}))
        purged = mm.working.purge_expired_retention()
        assert purged == 1
        assert mm.working.get("old") is None

    def test_episodic_erase_by_user(self) -> None:
        mm = MemoryManager()
        mm.episodic.append(
            MemoryRecord(content={}, user_tag=UserIsolationTag("u1"))
        )
        mm.episodic.append(
            MemoryRecord(content={}, user_tag=UserIsolationTag("u2"))
        )
        assert mm.episodic.erase_by_user("u1") == 1
        assert len(mm.episodic) == 1

    def test_semantic_erase_by_user(self) -> None:
        mm = MemoryManager()
        mm.semantic.store(
            MemoryRecord(memory_id="s1", content={}, user_tag=UserIsolationTag("u1"))
        )
        mm.semantic.store(
            MemoryRecord(memory_id="s2", content={}, user_tag=UserIsolationTag("u2"))
        )
        assert mm.semantic.erase_by_user("u1") == 1
        assert len(mm.semantic) == 1


class TestMemoryManagerGovernance:
    def test_forget_all_tiers(self) -> None:
        mm = MemoryManager()
        mm.working.put(
            MemoryRecord(content={}, user_tag=UserIsolationTag("alice"))
        )
        mm.episodic.append(
            MemoryRecord(content={}, user_tag=UserIsolationTag("alice"))
        )
        mm.semantic.store(
            MemoryRecord(content={}, user_tag=UserIsolationTag("alice"))
        )
        stats = mm.forget("alice")
        assert stats["working"] == 1
        assert stats["episodic"] == 1
        assert stats["semantic"] == 1
        assert len(mm.working) == 0
        assert len(mm.episodic) == 0
        assert len(mm.semantic) == 0

    def test_purge_expired_retention_all_tiers(self) -> None:
        mm = MemoryManager()
        old = MemoryRecord(content={"k": "v"})
        old.created_at = time.time() - 200 * 86400
        old.retention_days = 90
        mm.episodic.append(old)
        stats = mm.purge_expired_retention()
        assert stats["episodic"] == 1

    def test_governance_event_hook_fired(self) -> None:
        events: list[tuple[str, dict]] = []
        mm = MemoryManager(on_governance_event=lambda name, payload: events.append((name, payload)))
        mm.working.put(
            MemoryRecord(memory_id="g1", content={}, user_tag=UserIsolationTag("bob"))
        )
        mm.forget("bob")
        assert len(events) >= 1
        assert events[0][0] == "memory.forget"
