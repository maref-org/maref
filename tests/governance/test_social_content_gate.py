"""Tests for the social/content publishing risk gate (P3-C)."""

from __future__ import annotations

from pathlib import Path

from maref.governance.content_provenance import ProvenanceLedger
from maref.governance.social_content_gate import SocialContentGate, SocialContentRequest


def test_clean_content_is_allowed():
    decision = SocialContentGate().review(
        SocialContentRequest(platform="xiaohongshu", text="今天分享一个治理框架。")
    )
    assert decision.verdict == "allow"
    assert decision.allowed is True


def test_unknown_platform_is_blocked():
    decision = SocialContentGate().review(
        SocialContentRequest(platform="unknown", text="hello")
    )
    assert decision.verdict == "block"
    assert "unknown platform" in decision.reasons[0]


def test_length_limits_are_platform_specific():
    gate = SocialContentGate()
    too_long_x = gate.review(SocialContentRequest(platform="x", text="a" * 281))
    assert too_long_x.verdict == "block"
    allowed_wechat = gate.review(SocialContentRequest(platform="wechat", text="a" * 281))
    assert allowed_wechat.verdict == "allow"


def test_prohibited_financial_claim_is_blocked():
    decision = SocialContentGate().review(
        SocialContentRequest(platform="douyin", text="这个项目稳赚不赔，保证收益。")
    )
    assert decision.verdict == "block"
    assert "remove_prohibited_claim" in decision.required_actions


def test_absolute_claim_requires_review():
    decision = SocialContentGate().review(
        SocialContentRequest(platform="xiaohongshu", text="全网最低价的治理课程。")
    )
    assert decision.verdict == "review"
    assert decision.allowed is False
    assert "human_review_required" in decision.required_actions


def test_pii_is_blocked_and_redacted():
    decision = SocialContentGate().review(
        SocialContentRequest(
            platform="linkedin",
            text="联系我 13800138000 或 test@example.com",
        )
    )
    assert decision.verdict == "block"
    assert "[REDACTED:phone]" in decision.redacted_text
    assert "[REDACTED:email]" in decision.redacted_text


def test_ai_content_requires_disclosure():
    gate = SocialContentGate()
    missing = gate.review(
        SocialContentRequest(platform="bilibili", text="AI 生成的视频脚本。", ai_generated=True)
    )
    assert missing.verdict == "review"
    assert "add_ai_disclosure" in missing.required_actions

    present = gate.review(
        SocialContentRequest(
            platform="bilibili",
            text="AI 生成内容。AI 生成的视频脚本。",
            ai_generated=True,
            disclosure="AI 生成内容",
        )
    )
    assert present.verdict == "allow"


def test_unsupported_media_is_blocked():
    decision = SocialContentGate().review(
        SocialContentRequest(
            platform="douyin",
            text="视频内容",
            media_types=["application/x-msdownload"],
        )
    )
    assert decision.verdict == "block"
    assert "convert_media_type" in decision.required_actions


def test_provenance_license_is_checked(tmp_path: Path):
    ledger = ProvenanceLedger(tmp_path / "prov.jsonl")
    ledger.register("asset-1", content="payload", license="unknown")
    decision = SocialContentGate(provenance=ledger).review(
        SocialContentRequest(
            platform="xiaohongshu",
            text="内容",
            provenance_asset_id="asset-1",
        )
    )
    assert decision.verdict == "block"
    assert any("provenance" in reason for reason in decision.reasons)


def test_required_provenance_requires_review():
    decision = SocialContentGate(require_provenance=True).review(
        SocialContentRequest(platform="xiaohongshu", text="内容")
    )
    assert decision.verdict == "review"
    assert "register_provenance" in decision.required_actions


def test_pipeline_reviews_content_and_audits(tmp_path: Path):
    from maref.governance.governed_pipeline import GovernedPipeline

    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    decision = pipeline.review_social_content(
        SocialContentRequest(platform="xiaohongshu", text="今天分享一个治理框架。")
    )
    assert decision.verdict == "allow"
    entries = pipeline.audit.read_all()
    assert len(entries) == 1
    assert entries[0].event_type == "governance_decision"
    assert entries[0].action == "content.publish.xiaohongshu"


def test_pipeline_escalates_content_review(tmp_path: Path):
    from maref.governance.governed_pipeline import GovernedPipeline

    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    decision = pipeline.review_social_content(
        SocialContentRequest(platform="xiaohongshu", text="全网最低价的治理课程。")
    )
    assert decision.verdict == "review"
    entries = pipeline.audit.read_all()
    assert "ASK_USER" in entries[0].details


def test_pii_adjacent_to_chinese_text_is_redacted():
    decision = SocialContentGate().review(
        SocialContentRequest(platform="xiaohongshu", text="电话13800138000联系我")
    )
    assert decision.verdict == "block"
    assert "[REDACTED:phone]" in decision.redacted_text


def test_empty_allowed_licenses_denies_provenance():
    from maref.governance.content_provenance import ProvenanceLedger

    ledger = ProvenanceLedger()
    ledger.register("asset-2", content="payload", license="MIT")
    decision = SocialContentGate(provenance=ledger, allowed_licenses=[]).review(
        SocialContentRequest(
            platform="xiaohongshu", text="内容", provenance_asset_id="asset-2"
        )
    )
    assert decision.verdict == "block"


def _org_policy():
    from maref.governance.org_policy import OrganizationPolicy

    return OrganizationPolicy.from_dict(
        {
            "version": 1,
            "epoch": "2026-10-19",
            "organizations": {
                "acme": {
                    "roles": {
                        "坎": {
                            "allow": ["content.publish.*"],
                            "require_approval": ["content.publish.xiaohongshu"],
                        }
                    }
                }
            },
        }
    )


def test_pipeline_honors_org_policy_for_content(tmp_path: Path):
    from maref.governance.governed_pipeline import GovernedPipeline

    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=_org_policy(),
    )
    decision = pipeline.review_social_content(
        SocialContentRequest(
            platform="xiaohongshu",
            text="今天分享一个治理框架。",
            metadata={"tenant_id": "acme", "role": "坎"},
        )
    )
    assert decision.verdict == "review"
    assert decision.hitl_event_id
    assert "organization policy" in " ".join(decision.reasons)
