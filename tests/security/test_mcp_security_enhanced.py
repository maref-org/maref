from __future__ import annotations

import pytest

from maref.integration.mcp_security import (
    MCPSecurityGate,
    MCPTrustLevel,
    SecurityVerdict,
    ZeroTrustContext,
    RateLimiter,
    AuditLogEntry,
)


class TestMCPSecurityGateBasic:
    def test_trusted_always_allow(self):
        gate = MCPSecurityGate()
        result = gate.check("bash", MCPTrustLevel.TRUSTED)
        assert result == SecurityVerdict.ALLOW

    def test_untrusted_blocked_tool(self):
        gate = MCPSecurityGate()
        result = gate.check("bash", MCPTrustLevel.UNTRUSTED)
        assert result == SecurityVerdict.DENY

    def test_untrusted_blocked_pattern(self):
        gate = MCPSecurityGate()
        result = gate.check("safe_tool", MCPTrustLevel.UNTRUSTED, {"command": "rm -rf /"})
        assert result == SecurityVerdict.DENY

    def test_untrusted_allowed_tool(self):
        gate = MCPSecurityGate()
        result = gate.check("safe_tool", MCPTrustLevel.UNTRUSTED, {"input": "hello"})
        assert result == SecurityVerdict.AUDIT

    def test_semi_trusted_blocked_tool(self):
        gate = MCPSecurityGate()
        result = gate.check("bash", MCPTrustLevel.SEMI_TRUSTED)
        assert result == SecurityVerdict.DENY

    def test_semi_trusted_allowed_tool(self):
        gate = MCPSecurityGate()
        result = gate.check("safe_tool", MCPTrustLevel.SEMI_TRUSTED)
        assert result == SecurityVerdict.AUDIT


class TestZeroTrustContext:
    def test_delegation_depth_limit(self):
        gate = MCPSecurityGate(max_delegation_depth=3)
        context = ZeroTrustContext(delegation_depth=4)
        result = gate.check("safe_tool", MCPTrustLevel.TRUSTED, context=context)
        assert result == SecurityVerdict.DENY

    def test_delegation_depth_ok(self):
        gate = MCPSecurityGate(max_delegation_depth=5)
        context = ZeroTrustContext(delegation_depth=3)
        result = gate.check("safe_tool", MCPTrustLevel.TRUSTED, context=context)
        assert result == SecurityVerdict.ALLOW


class TestRateLimiter:
    def test_rate_limit_exceeded(self):
        gate = MCPSecurityGate(
            enable_rate_limiting=True,
            rate_limiter=RateLimiter(max_requests=2, window_seconds=60),
        )
        # First 2 requests should succeed
        assert gate.check("tool1", MCPTrustLevel.TRUSTED) == SecurityVerdict.ALLOW
        assert gate.check("tool2", MCPTrustLevel.TRUSTED) == SecurityVerdict.ALLOW
        # Third request should be denied
        result = gate.check("tool3", MCPTrustLevel.TRUSTED)
        assert result == SecurityVerdict.DENY

    def test_rate_limit_disabled(self):
        gate = MCPSecurityGate(enable_rate_limiting=False)
        # Should allow many requests
        for _ in range(10):
            assert gate.check("tool", MCPTrustLevel.TRUSTED) == SecurityVerdict.ALLOW


class TestAuditLogging:
    def test_audit_log_created(self):
        gate = MCPSecurityGate(enable_audit_logging=True)
        context = ZeroTrustContext(agent_id="agent-001")
        gate.check("safe_tool", MCPTrustLevel.UNTRUSTED, {"input": "hello"}, context=context)
        
        log = gate.get_audit_log()
        assert len(log) == 1
        assert log[0].agent_id == "agent-001"
        assert log[0].tool_name == "safe_tool"

    def test_audit_log_disabled(self):
        gate = MCPSecurityGate(enable_audit_logging=False)
        gate.check("tool", MCPTrustLevel.TRUSTED)
        assert len(gate.get_audit_log()) == 0

    def test_audit_summary(self):
        gate = MCPSecurityGate()
        gate.check("tool1", MCPTrustLevel.TRUSTED)
        gate.check("bash", MCPTrustLevel.UNTRUSTED)
        gate.check("tool3", MCPTrustLevel.SEMI_TRUSTED)
        
        summary = gate.get_audit_summary()
        assert summary["total_requests"] == 3
        assert summary["allowed"] == 1
        assert summary["denied"] == 1
        assert summary["audited"] == 1

    def test_export_json(self):
        gate = MCPSecurityGate()
        gate.check("tool", MCPTrustLevel.TRUSTED)
        
        json_output = gate.export_audit_log("json")
        assert "timestamp" in json_output
        assert "tool" in json_output

    def test_export_syslog(self):
        gate = MCPSecurityGate()
        gate.check("tool", MCPTrustLevel.TRUSTED)
        
        syslog_output = gate.export_audit_log("syslog")
        assert "MAREF-SECURITY" in syslog_output
        assert "agent=" in syslog_output


class TestRiskCalculation:
    def test_high_risk_untrusted_deep(self):
        gate = MCPSecurityGate()
        context = ZeroTrustContext(delegation_depth=5)
        result = gate.check("bash", MCPTrustLevel.UNTRUSTED, {"cmd": "rm file"}, context=context)
        assert result == SecurityVerdict.DENY
        
        log = gate.get_audit_log()
        assert log[0].risk_score > 0.7

    def test_low_risk_trusted(self):
        gate = MCPSecurityGate()
        context = ZeroTrustContext(delegation_depth=0)
        gate.check("safe_tool", MCPTrustLevel.TRUSTED, context=context)
        
        log = gate.get_audit_log()
        assert log[0].risk_score < 0.3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
