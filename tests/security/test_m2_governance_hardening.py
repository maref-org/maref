"""M2 补强测试：TrustBoundary 防伪 + 消毒链路接线（C-3 / H-1 / H-2）。

依据 docs/audit-reports/audit-reinforcement-20260805-v0.52.md
- C-3: 分级输入自报可信 + scope 防伪恒失效
- H-1: 消毒链路零生产调用
- H-2: sanitizer 授权还原无鉴权
"""

from __future__ import annotations

import pytest

from maref.governance.risk_classifier import (
    RiskLevel,
    classify_action_server,
)
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.identity.credential import AuthorizationScope
from maref.security.sanitizer import Sanitizer

# ── C-3a: 分级服务端权重 ──────────────────────────────────────────────


class TestClassifyActionServer:
    def test_irreversible_prefix_cannot_be_downgraded_by_metadata(self) -> None:
        """调用方 metadata 声称 local/reversible 也不能把 delete:/payment: 降级。"""
        assessment = classify_action_server(
            "payment:transfer",
            metadata={"impact_scope": "local", "reversible": True},
        )
        assert assessment.risk_level == RiskLevel.IRREVERSIBLE

    def test_sensitive_term_cannot_be_downgraded_by_metadata(self) -> None:
        """metadata 声称 local 也不能把含 delete 的动作降为 LOW。"""
        assessment = classify_action_server(
            "file.delete",
            metadata={"impact_scope": "local", "reversible": True},
        )
        assert assessment.risk_level == RiskLevel.HIGH

    def test_global_impact_raises_risk(self) -> None:
        """服务端可信字段仍可升级风险（global → HIGH）。"""
        assessment = classify_action_server(
            "file.read",
            metadata={"impact_scope": "local"},
            trusted={"impact_scope": "global"},
        )
        assert assessment.risk_level == RiskLevel.HIGH

    def test_metadata_cannot_lower_action_derived_level(self) -> None:
        """动作字符串推导出的等级是下限，metadata 只能升不能降。"""
        assessment = classify_action_server(
            "deploy:app",
            metadata={"impact_scope": "local", "reversible": True},
        )
        assert assessment.risk_level == RiskLevel.IRREVERSIBLE


# ── C-3b: scope 防伪 ─────────────────────────────────────────────────


class TestTrustBoundaryScopeAntiForgery:
    def _make_signed_scope(self) -> tuple[AuthorizationScope, str]:
        from maref.signing.signing_key import ReportSigningKey

        key = ReportSigningKey.generate()
        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
            issuer="trusted-issuer",
        )
        scope.sign(key)
        return scope, key.public_key_pem

    def test_unsigned_scope_from_untrusted_dict_is_rejected(self) -> None:
        """伪造 scope（issuer 无签名）在配置了公钥时被拒绝。"""
        scope = AuthorizationScope(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
            issuer="trusted-issuer",
            signature="",
        )
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"trusted-issuer": "any-pem"},
        )
        decision = boundary.check_no_raise(
            "network:medical_record", agent_id="agent-01"
        )
        assert decision.allowed is False

    def test_signed_scope_with_valid_key_allowed(self) -> None:
        scope, pub_pem = self._make_signed_scope()
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"trusted-issuer": pub_pem},
        )
        decision = boundary.check_no_raise(
            "network:medical_record", agent_id="agent-01"
        )
        assert decision.allowed is True

    def test_signed_scope_with_wrong_key_blocked(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        scope, _ = self._make_signed_scope()
        other = ReportSigningKey.generate()
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"trusted-issuer": other.public_key_pem},
        )
        decision = boundary.check_no_raise(
            "network:medical_record", agent_id="agent-01"
        )
        assert decision.allowed is False

    def test_scope_with_issuer_but_no_key_configured_is_fail_closed(self) -> None:
        """签名 scope 的 issuer 无公钥配置时 fail-closed，防止伪造 scope 冒充。"""
        scope = AuthorizationScope(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
            issuer="untrusted-issuer",
            signature="fake-signature",
        )
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check_no_raise(
            "network:medical_record", agent_id="agent-01"
        )
        assert decision.allowed is False


# ── H-1: 消毒链路生产接线 ─────────────────────────────────────────────


class TestSanitizerProductionWiring:
    def test_data_sovereignty_manager_sanitizes_by_category(self) -> None:
        """C1→C2→C3 生产锚点：数据主权管理器按分类消毒。"""
        from maref.compliance.data_sovereignty import DataCategory, DataSovereigntyManager

        mgr = DataSovereigntyManager()
        result = mgr.sanitize_data("电话 13800138000", DataCategory.HEALTH)
        assert "13800138000" not in result.text
        assert "[PII_" in result.text

    def test_middleware_sanitizes_outbound_payload(self) -> None:
        """真实数据路径：跨境放行的 data_transfer payload 必须被分类消毒。"""
        from maref.compliance.data_sovereignty import DataSovereigntyManager
        from maref.integration.mcp_security_middleware import DataSovereigntyMiddleware
        from maref.integration.mcp_transport import JSONRPCRequest

        mw = DataSovereigntyMiddleware(DataSovereigntyManager())
        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="tools/call",
            id=1,
            params={
                "data_transfer": {
                    "source_country": "CN",
                    "destination_country": "US",
                    "data_class_ids": ["public"],
                    "purpose": "publish",
                    "payload": "电话 13800138000",
                }
            },
        )
        result = mw.process(request, agent_id="agent-01")
        assert result.is_allowed is True
        assert result.sanitized_payload is not None
        assert "13800138000" not in result.sanitized_payload
        assert "[PII_" in result.sanitized_payload

    def test_chain_propagates_sanitized_payload(self) -> None:
        """中间件链：MCPSecurityMiddleware 放行时传播消毒后 payload。"""
        from maref.compliance.data_sovereignty import DataSovereigntyManager
        from maref.integration.mcp_security_middleware import MCPSecurityMiddleware
        from maref.integration.mcp_transport import JSONRPCRequest

        mw = MCPSecurityMiddleware(data_sovereignty_manager=DataSovereigntyManager())
        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="tools/call",
            id=1,
            params={
                "name": "file.write",
                "arguments": {},
                "data_transfer": {
                    "source_country": "CN",
                    "destination_country": "US",
                    "data_class_ids": ["public"],
                    "purpose": "publish",
                    "payload": "电话 13800138000",
                },
            },
        )
        result = mw.process(request, agent_id="agent-01")
        assert result.is_allowed is True
        assert result.sanitized_payload is not None
        assert "13800138000" not in result.sanitized_payload
        assert "[PII_" in result.sanitized_payload


# ── H-2: 还原鉴权 ─────────────────────────────────────────────────────


class TestSanitizerRestoreAuthorization:
    def test_restore_requires_principal_when_authorized(self) -> None:
        """authorized=True 必须提供 authorized_by 身份，否则拒绝。"""
        sani = Sanitizer()
        result = sani.sanitize_input("电话 13800138000")
        with pytest.raises(ValueError):
            sani.restore_output(
                result.text, result.tokens, authorized=True, authorized_by=None
            )

    def test_restore_with_principal_restores(self) -> None:
        sani = Sanitizer()
        text = "电话 13800138000"
        result = sani.sanitize_input(text)
        restored = sani.restore_output(
            result.text, result.tokens, authorized=True, authorized_by="agent-01"
        )
        assert restored == text

    def test_restore_without_authorization_keeps_tokens(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("电话 13800138000")
        out = sani.restore_output(result.text, result.tokens)
        assert "[PII_" in out
        assert "13800138000" not in out

    def test_restore_records_audit_entry(self) -> None:
        entries: list[dict] = []

        class FakeAudit:
            def log(self, **kw) -> None:
                entries.append(kw)

        sani = Sanitizer(audit_logger=FakeAudit())
        result = sani.sanitize_input("电话 13800138000")
        sani.restore_output(
            result.text, result.tokens, authorized=True, authorized_by="agent-01"
        )
        assert len(entries) == 1
        assert entries[0]["actor"] == "agent-01"
        assert entries[0]["event_type"] == "pii_restore"
