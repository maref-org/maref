"""Tests for WeightAuditorAdapter — TransformerLens weight auditing.

Covers:
- Degraded mode when transformer_lens is not installed
- Degraded report fields (backdoor_suspected=False, confidence=0.0)
- available property is bool
- VerifierEntry metadata registration
- WeightAuditReport.to_dict()
"""

from __future__ import annotations

from maref.security.weight_auditor import (
    WeightAuditReport,
    WeightAuditorAdapter,
    register_weight_auditor_verifier,
)


class TestWeightAuditorAdapter:
    def test_available_property_is_bool(self) -> None:
        """初始化后 available 属性为 bool."""
        auditor = WeightAuditorAdapter()
        assert isinstance(auditor.available, bool)

    def test_unavailable_returns_degraded_report(self) -> None:
        """transformer_lens 未安装时 audit() 返回降级报告."""
        # 构造一个 _available=False 的实例
        auditor = WeightAuditorAdapter()
        if auditor.available:
            # 如果环境装了 transformer_lens，手动模拟 unavailable 场景
            auditor._available = False

        report = auditor.audit("gpt2", trigger_patterns=["trigger_word"])
        assert report.backdoor_suspected is False
        assert report.confidence == 0.0
        assert report.anomalous_activations == []
        assert "not installed" in report.details

    def test_degraded_report_fields(self) -> None:
        """降级报告所有字段符合预期."""
        auditor = WeightAuditorAdapter()
        if auditor.available:
            auditor._available = False

        report = auditor.audit("some-model")
        assert report.model_id == "some-model"
        assert report.backdoor_suspected is False
        assert report.confidence == 0.0
        assert report.anomalous_activations == []
        assert "transformer_lens not installed" in report.details
        assert "pip install maref[audit]" in report.details

    def test_audit_returns_weight_audit_report_type(self) -> None:
        """audit() 返回 WeightAuditReport 类型."""
        auditor = WeightAuditorAdapter()
        report = auditor.audit("test-model")
        assert isinstance(report, WeightAuditReport)

    def test_audit_with_empty_triggers_in_degraded_mode(self) -> None:
        """降级模式下即使 trigger_patterns 为空也不崩溃."""
        auditor = WeightAuditorAdapter()
        if auditor.available:
            auditor._available = False

        report = auditor.audit("model", trigger_patterns=[])
        assert report.backdoor_suspected is False


class TestWeightAuditReport:
    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict() 含所有字段."""
        report = WeightAuditReport(
            model_id="test-model",
            backdoor_suspected=True,
            anomalous_activations=["layer0:trigger"],
            confidence=0.85,
            details="Found anomalies",
        )
        d = report.to_dict()
        assert d["model_id"] == "test-model"
        assert d["backdoor_suspected"] is True
        assert d["anomalous_activations"] == ["layer0:trigger"]
        assert d["confidence"] == 0.85
        assert d["details"] == "Found anomalies"

    def test_default_degraded_report_dict(self) -> None:
        """降级报告的 to_dict() 字段正确."""
        auditor = WeightAuditorAdapter()
        if auditor.available:
            auditor._available = False

        report = auditor.audit("degraded-model")
        d = report.to_dict()
        assert d["model_id"] == "degraded-model"
        assert d["backdoor_suspected"] is False
        assert d["confidence"] == 0.0
        assert d["anomalous_activations"] == []


class TestRegisterWeightAuditorVerifier:
    def test_registers_verifier_entry(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry, VerifierStatus

        registry = VerifierRegistry()
        register_weight_auditor_verifier(registry)

        entry = registry.get("weight_auditor")
        assert entry is not None
        assert entry.model == "TransformerLens v1"
        assert entry.methodology == "activation_pattern_analysis"
        assert entry.status == VerifierStatus.ACTIVE
        assert entry.accuracy == 0.0
        assert entry.recall == 0.0

    def test_registered_verifier_listed_active(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry

        registry = VerifierRegistry()
        register_weight_auditor_verifier(registry)

        active = registry.list_active()
        names = [v.name for v in active]
        assert "weight_auditor" in names


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
