from __future__ import annotations

import json
import os
import tempfile

from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.hitl import HITLRouter
from maref.integration.mcp_client import ConnectionState, MCPClient, MCPConnection
from maref.integration.mcp_governance import (
    HMAC_SECRET_KEY,
    AllowKnownSafeMCPTools,
    AllowMCPProtocolSignals,
    BlockDangerousArgs,
    BlockDangerousMCPTools,
    MCPCircuitBreakerMonitor,
    MCPDecisionVerdict,
    MCPGovernance,
    MCPGovernanceResult,
    MCPMappedPolicyEngine,
    MCPPolicyContext,
    MCPPolicyEngine,
    MCPPolicyMapping,
    MCPPolicyRule,
    MCPToolCallStats,
    TrustLevelBasedGate,
    WriteToolRequiresHITL,
    sign_audit_entry,
    verify_audit_signature,
)
from maref.integration.mcp_security import (
    AuditLogEntry,
    MCPSecurityGate,
    MCPTrustLevel,
)
from maref.integration.mcp_transport import (
    JSONRPCResponse,
    MCPTransport,
)


class MockTransport(MCPTransport):
    """Mock transport that returns canned responses without real I/O."""

    def __init__(self, response: JSONRPCResponse | None = None):
        super().__init__()
        self._response = response or JSONRPCResponse(
            jsonrpc="2.0",
            result={"serverInfo": {"name": "mock", "version": "1.0"}},
            id=1,
        )
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, request):
        return self._response

    def send_initialize(self):
        return self._response

    def send_tools_list(self):
        return self._response

    def send_tool_call(self, tool_name: str, args: dict):
        return self._response

    def send_resources_list(self):
        return self._response


# ============================================================================
# E1.1-A1: MCPGovernance.evaluate() 返回 ALLOW/DENY/ASK_USER
# ============================================================================


class TestMCPDecisionVerdict:
    def test_enum_values(self):
        assert MCPDecisionVerdict.ALLOW.value == "allow"
        assert MCPDecisionVerdict.DENY.value == "deny"
        assert MCPDecisionVerdict.ASK_USER.value == "ask_user"


class TestMCPPolicyContext:
    def test_default_creation(self):
        ctx = MCPPolicyContext(tool_name="test_tool")
        assert ctx.tool_name == "test_tool"
        assert ctx.args == {}
        assert ctx.trust_level == MCPTrustLevel.UNTRUSTED
        assert ctx.agent_id == ""
        assert ctx.delegation_depth == 0

    def test_full_creation(self):
        ctx = MCPPolicyContext(
            tool_name="shell_exec",
            args={"command": "ls"},
            trust_level=MCPTrustLevel.SEMI_TRUSTED,
            agent_id="agent-001",
            session_id="session-001",
            chain_id="chain-001",
            delegation_depth=2,
            request_id="req-001",
        )
        assert ctx.tool_name == "shell_exec"
        assert ctx.args == {"command": "ls"}
        assert ctx.trust_level == MCPTrustLevel.SEMI_TRUSTED


class TestMCPGovernanceResult:
    def test_default_creation(self):
        result = MCPGovernanceResult(verdict=MCPDecisionVerdict.ALLOW)
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.reason == ""
        assert result.risk_score == 0.0
        assert result.hitl_event_id is None

    def test_to_dict(self):
        result = MCPGovernanceResult(
            verdict=MCPDecisionVerdict.ALLOW,
            reason="Safe tool",
            risk_score=0.1,
            audit_signature="abc123",
            matched_rule="rule-001",
        )
        d = result.to_dict()
        assert d["verdict"] == "allow"
        assert d["reason"] == "Safe tool"
        assert d["risk_score"] == 0.1
        assert d["audit_signature"] == "abc123"
        assert d["matched_rule"] == "rule-001"


# ============================================================================
# Policy Rules
# ============================================================================


class TestAllowMCPProtocolSignals:
    def test_allows_ping(self):
        rule = AllowMCPProtocolSignals()
        ctx = MCPPolicyContext(tool_name="ping")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.matched_rule == "mcp-rule-001"

    def test_allows_tools_list(self):
        rule = AllowMCPProtocolSignals()
        ctx = MCPPolicyContext(tool_name="tools/list")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_allows_resources_list(self):
        rule = AllowMCPProtocolSignals()
        ctx = MCPPolicyContext(tool_name="resources/list")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_allows_prompts_get(self):
        rule = AllowMCPProtocolSignals()
        ctx = MCPPolicyContext(tool_name="prompts/get")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_passes_non_protocol_tool(self):
        rule = AllowMCPProtocolSignals()
        ctx = MCPPolicyContext(tool_name="custom_tool")
        result = rule.evaluate(ctx)
        assert result is None


class TestAllowKnownSafeMCPTools:
    def test_allows_read_tool(self):
        rule = AllowKnownSafeMCPTools()
        ctx = MCPPolicyContext(tool_name="read_file")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_allows_list_tool(self):
        rule = AllowKnownSafeMCPTools()
        ctx = MCPPolicyContext(tool_name="list_directory")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_allows_safe_prefix_tool(self):
        rule = AllowKnownSafeMCPTools()
        ctx = MCPPolicyContext(tool_name="status_check")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_passes_unknown_tool(self):
        rule = AllowKnownSafeMCPTools()
        ctx = MCPPolicyContext(tool_name="write_file")
        result = rule.evaluate(ctx)
        assert result is None


class TestBlockDangerousMCPTools:
    def test_asks_for_shell_tool(self):
        rule = BlockDangerousMCPTools()
        ctx = MCPPolicyContext(tool_name="shell")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.risk_score == 0.9

    def test_asks_for_bash_tool(self):
        rule = BlockDangerousMCPTools()
        ctx = MCPPolicyContext(tool_name="bash")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_asks_for_exec_tool(self):
        rule = BlockDangerousMCPTools()
        ctx = MCPPolicyContext(tool_name="exec_command")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_passes_safe_tool(self):
        rule = BlockDangerousMCPTools()
        ctx = MCPPolicyContext(tool_name="read_file")
        result = rule.evaluate(ctx)
        assert result is None

    def test_dangerous_substring_matches(self):
        rule = BlockDangerousMCPTools()
        ctx = MCPPolicyContext(tool_name="custom_shell_wrapper")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER


class TestBlockDangerousArgs:
    def test_blocks_rm_rf(self):
        rule = BlockDangerousArgs()
        ctx = MCPPolicyContext(tool_name="execute", args={"command": "rm -rf /"})
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.DENY
        assert result.risk_score == 1.0

    def test_blocks_drop_table(self):
        rule = BlockDangerousArgs()
        ctx = MCPPolicyContext(tool_name="query", args={"sql": "DROP TABLE users"})
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.DENY

    def test_blocks_sudo(self):
        rule = BlockDangerousArgs()
        ctx = MCPPolicyContext(tool_name="execute", args={"command": "sudo rm file"})
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.DENY

    def test_allows_safe_args(self):
        rule = BlockDangerousArgs()
        ctx = MCPPolicyContext(tool_name="execute", args={"command": "ls -la"})
        result = rule.evaluate(ctx)
        assert result is None

    def test_allows_empty_args(self):
        rule = BlockDangerousArgs()
        ctx = MCPPolicyContext(tool_name="list")
        result = rule.evaluate(ctx)
        assert result is None


class TestWriteToolRequiresHITL:
    def test_asks_for_write_file(self):
        rule = WriteToolRequiresHITL()
        ctx = MCPPolicyContext(tool_name="write_file")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.risk_score == 0.7

    def test_asks_for_delete(self):
        rule = WriteToolRequiresHITL()
        ctx = MCPPolicyContext(tool_name="delete_file")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_asks_for_push(self):
        rule = WriteToolRequiresHITL()
        ctx = MCPPolicyContext(tool_name="push_changes")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_asks_for_send(self):
        rule = WriteToolRequiresHITL()
        ctx = MCPPolicyContext(tool_name="send_email")
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_passes_read_tool(self):
        rule = WriteToolRequiresHITL()
        ctx = MCPPolicyContext(tool_name="read_file")
        result = rule.evaluate(ctx)
        assert result is None


class TestTrustLevelBasedGate:
    def test_trusted_allows(self):
        rule = TrustLevelBasedGate()
        ctx = MCPPolicyContext(tool_name="any_tool", trust_level=MCPTrustLevel.TRUSTED)
        result = rule.evaluate(ctx)
        assert result is None

    def test_untrusted_asks_for_shell(self):
        rule = TrustLevelBasedGate()
        ctx = MCPPolicyContext(
            tool_name="bash",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.DENY

    def test_untrusted_asks_for_safe_tool(self):
        rule = TrustLevelBasedGate()
        ctx = MCPPolicyContext(
            tool_name="read_file",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_custom_security_gate(self):
        gate = MCPSecurityGate(allow_untrusted_shell=True)
        rule = TrustLevelBasedGate(security_gate=gate)
        ctx = MCPPolicyContext(
            tool_name="bash",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.verdict == MCPDecisionVerdict.ASK_USER


# ============================================================================
# MCPPolicyEngine
# ============================================================================


class TestMCPPolicyEngine:
    def test_default_rules_allow_protocol_signal(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="ping")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.matched_rule == "mcp-rule-001"

    def test_default_rules_allow_safe_tool(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="read_file", trust_level=MCPTrustLevel.UNTRUSTED)
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.matched_rule == "mcp-rule-002"

    def test_default_rules_asks_for_shell(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="shell_exec", trust_level=MCPTrustLevel.UNTRUSTED)
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.matched_rule == "mcp-rule-003"

    def test_default_rules_blocks_dangerous_args(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="run_script", args={"command": "rm -rf /"})
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.DENY
        assert result.matched_rule == "mcp-rule-004"

    def test_default_rules_asks_for_write_tool(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="write_file", trust_level=MCPTrustLevel.TRUSTED)
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.matched_rule == "mcp-rule-005"

    def test_default_fallback(self):
        engine = MCPPolicyEngine()
        ctx = MCPPolicyContext(tool_name="unknown_custom_tool", trust_level=MCPTrustLevel.TRUSTED)
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.matched_rule == "default"

    def test_custom_rules(self):
        class AlwaysDeny(MCPPolicyRule):
            def __init__(self):
                super().__init__(rule_id="custom-deny", description="Always deny", priority=999)

            def evaluate(self, context):
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY, reason="Custom deny", matched_rule=self.rule_id
                )

        engine = MCPPolicyEngine(rules=[AlwaysDeny()])
        ctx = MCPPolicyContext(tool_name="any_tool")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.DENY
        assert result.matched_rule == "custom-deny"

    def test_add_remove_rule(self):
        engine = MCPPolicyEngine()

        class TestRule(MCPPolicyRule):
            def __init__(self):
                super().__init__(rule_id="test-rule", description="Test", priority=50)

            def evaluate(self, context):
                return MCPGovernanceResult(verdict=MCPDecisionVerdict.DENY, reason="Test")

        rule = TestRule()
        engine.add_rule(rule)
        assert len(engine.get_rules()) == 7  # 6 default + 1 added

        removed = engine.remove_rule("test-rule")
        assert removed is True
        assert len(engine.get_rules()) == 6

        removed = engine.remove_rule("nonexistent")
        assert removed is False


# ============================================================================
# E1.1-A2: HMAC-SHA256 Audit Logging
# ============================================================================


class TestHMACAuditSigning:
    def test_sign_and_verify_entry(self):
        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="read_file",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc123",
            chain_id="chain-001",
            delegation_depth=1,
            risk_score=0.1,
        )
        signature = sign_audit_entry(entry, HMAC_SECRET_KEY)
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

        is_valid = verify_audit_signature(entry, signature, HMAC_SECRET_KEY)
        assert is_valid is True

    def test_tampered_entry_fails_verification(self):
        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="read_file",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc123",
        )
        signature = sign_audit_entry(entry, HMAC_SECRET_KEY)

        entry.tool_name = "write_file"
        is_valid = verify_audit_signature(entry, signature, HMAC_SECRET_KEY)
        assert is_valid is False

    def test_wrong_key_fails_verification(self):
        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="read_file",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc123",
        )
        signature = sign_audit_entry(entry, b"different-key")
        is_valid = verify_audit_signature(entry, signature, HMAC_SECRET_KEY)
        assert is_valid is False

    def test_different_args_hash_different_signature(self):
        entry1 = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="read_file",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc",
        )
        entry2 = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="read_file",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="def",
        )
        sig1 = sign_audit_entry(entry1, HMAC_SECRET_KEY)
        sig2 = sign_audit_entry(entry2, HMAC_SECRET_KEY)
        assert sig1 != sig2


# ============================================================================
# E1.1-A3 + A4: Full MCPGovernance Pipeline
# ============================================================================


class TestMCPGovernance:
    def test_allows_safe_tool(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="read_file",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        assert result.verdict == MCPDecisionVerdict.ALLOW
        assert result.audit_signature != ""
        assert len(gov.get_audit_log()) == 1
        assert len(gov.get_decision_log()) == 1

    def test_denies_dangerous_args(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="run_script",
            args={"command": "rm -rf /"},
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        assert result.verdict == MCPDecisionVerdict.DENY
        assert result.risk_score == 1.0

    def test_asks_user_for_shell(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="shell_exec",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.hitl_event_id is not None
        assert result.hitl_tier is not None

    def test_asks_user_for_write_tool(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="write_file",
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.hitl_event_id is not None

    def test_audit_log_contains_all_decisions(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")
        gov.evaluate(tool_name="run_script", args={"command": "rm -rf /"}, agent_id="agent-001")

        log = gov.get_audit_log()
        assert len(log) == 3

        verdicts = [e.verdict for e in log]
        assert "ALLOW" in verdicts
        assert "ASK_USER" in verdicts
        assert "DENY" in verdicts

    def test_audit_summary_counts(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="run_script", args={"command": "rm -rf /"}, agent_id="agent-001")

        summary = gov.get_audit_summary()
        assert summary["total_calls"] == 3
        assert summary["allowed"] == 2
        assert summary["denied"] == 1

    def test_circuit_breaker_integration(self):
        gov = MCPGovernance()
        cb = gov.circuit_breaker
        assert cb.state.value == "closed"

        for _ in range(5):
            gov.evaluate(tool_name="run_script", args={"command": "rm -rf /"}, agent_id="agent-001")

        # After 5 denials, CB should be open
        result = gov.evaluate(tool_name="read_file", agent_id="agent-001")
        assert result.verdict == MCPDecisionVerdict.DENY
        assert "circuit_breaker" in result.matched_rule

    def test_audit_log_has_hmac_signatures(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")

        log = gov.get_audit_log()
        assert len(log) == 1

        dec = gov.get_decision_log()
        assert len(dec) == 1
        assert dec[0].audit_signature != ""

        sig = dec[0].metadata.get("audit_signature", "")
        assert sig != ""

    def test_export_audit_log_json(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")

        exported = gov.export_audit_log(format="json")
        data = json.loads(exported)
        assert len(data) == 2
        assert data[0]["tool_name"] == "read_file"
        assert data[1]["tool_name"] == "write_file"

    def test_circuit_breaker_records_success(self):
        gov = MCPGovernance()
        cb = gov.circuit_breaker

        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        assert cb._failure_count == 0  # success resets

    def test_hitl_approve_and_reject(self):
        gov = MCPGovernance()
        result = gov.evaluate(tool_name="shell_exec", agent_id="agent-001")
        assert result.verdict == MCPDecisionVerdict.ASK_USER
        assert result.hitl_event_id is not None

        approved = gov.approve_tool_call(result.hitl_event_id, "human")
        assert approved is True

        result2 = gov.evaluate(tool_name="write_file", agent_id="agent-001")
        assert result2.hitl_event_id is not None

        rejected = gov.reject_tool_call(result2.hitl_event_id, "Not needed")
        assert rejected is True

    def test_custom_components(self):
        cb = CircuitBreaker(max_depth=5, max_consecutive_failures=10)
        hitl = HITLRouter()
        gov = MCPGovernance(circuit_breaker=cb, hitl_router=hitl)

        assert gov.circuit_breaker is cb
        assert gov.hitl_router is hitl

    def test_evaluate_with_delegation_depth(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="read_file",
            trust_level=MCPTrustLevel.TRUSTED,
            agent_id="agent-001",
            delegation_depth=3,
        )
        # Should still allow at depth 3
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_policy_engine_customization(self):
        engine = MCPPolicyEngine()
        gov = MCPGovernance(policy_engine=engine)
        assert gov.policy_engine is engine


# ============================================================================
# E1.1-A4: MCPClient Integration
# ============================================================================


class TestMCPClientGovernanceIntegration:
    def test_client_can_register_governance(self):
        client = MCPClient()
        gov = MCPGovernance()
        client.register_governance(gov)
        assert client._governance is gov

    def test_client_no_governance_by_default(self):
        client = MCPClient()
        assert client._governance is None


class TestGovernedCallTool:
    def test_mcp_client_safe_mcp_tool_call_governed(self):
        client = MCPClient()
        mock_transport = MockTransport()
        conn = MCPConnection(
            transport=mock_transport,
            config_hash="test-hash",
            state=ConnectionState.CONNECTED,
            session_id="test-session",
        )
        client._connections["test"] = conn

        gov = MCPGovernance()
        client.register_governance(gov)

        result = client.call_tool(
            conn=conn,
            tool_name="read_file",
            args={},
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )

        assert result is not None
        assert result.error is None or not result.is_error

        gov_log = gov.get_audit_log()
        assert len(gov_log) >= 1

    def test_mcp_client_denies_dangerous_tool_call(self):
        client = MCPClient()
        mock_transport = MockTransport()
        conn = MCPConnection(
            transport=mock_transport,
            config_hash="test-hash",
            state=ConnectionState.CONNECTED,
            session_id="test-session",
        )
        client._connections["test"] = conn

        gov = MCPGovernance()
        client.register_governance(gov)

        result = client.call_tool(
            conn=conn,
            tool_name="run_script",
            args={"command": "rm -rf /"},
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-001",
        )

        assert result.is_error
        assert "Governance denied" in (result.error or {}).get("message", "")

    def test_governance_not_registered_passthrough(self):
        client = MCPClient()
        mock_transport = MockTransport()
        conn = MCPConnection(
            transport=mock_transport,
            config_hash="test-hash",
            state=ConnectionState.CONNECTED,
            session_id="test-session",
        )
        client._connections["test"] = conn

        result = client.call_tool(
            conn=conn,
            tool_name="shell_exec",
            args={"command": "ls"},
        )
        assert result is not None
        assert not result.is_error


# ============================================================================
# Integration: HMAC in mcp_security.py
# ============================================================================


class TestMCPSecurityHMACIntegration:
    def test_sign_audit_entry_standalone(self):
        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="test_tool",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc123",
        )
        from maref.integration.mcp_security import sign_audit_entry as sec_sign

        sig = sec_sign(entry)
        assert len(sig) == 64

    def test_security_module_verify(self):
        entry = AuditLogEntry(
            timestamp=__import__("datetime").datetime(2026, 5, 20, 12, 0, 0),
            agent_id="agent-001",
            tool_name="test_tool",
            trust_level="trusted",
            verdict="ALLOW",
            args_hash="abc123",
        )
        from maref.integration.mcp_security import sign_audit_entry as sec_sign
        from maref.integration.mcp_security import verify_audit_signature as sec_verify

        sig = sec_sign(entry)
        assert sec_verify(entry, sig) is True

    def test_cross_module_compatibility(self):
        from maref.integration.mcp_governance import HMAC_SECRET_KEY as GOV_KEY
        from maref.integration.mcp_security import DEFAULT_HMAC_SECRET_KEY as SEC_KEY

        assert SEC_KEY == GOV_KEY


# ============================================================================
# E1.2: Circuit Breaker Monitor
# ============================================================================


class TestMCPToolCallStats:
    def test_default_values(self):
        stats = MCPToolCallStats(tool_name="test_tool")
        assert stats.tool_name == "test_tool"
        assert stats.call_count == 0
        assert stats.error_count == 0
        assert stats.avg_latency == 0.0
        assert stats.error_rate == 0.0

    def test_avg_latency(self):
        stats = MCPToolCallStats(tool_name="t", call_count=2, total_latency=10.0)
        assert stats.avg_latency == 5.0

    def test_error_rate(self):
        stats = MCPToolCallStats(tool_name="t", call_count=4, error_count=1)
        assert stats.error_rate == 0.25


class TestMCPCircuitBreakerMonitor:
    def test_record_call_success(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("read_file", 0.1, success=True)
        stats = monitor.get_tool_stats("read_file")
        assert stats is not None
        assert stats.call_count == 1
        assert stats.error_count == 0

    def test_record_call_error(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("shell_exec", 0.5, success=False)
        stats = monitor.get_tool_stats("shell_exec")
        assert stats.call_count == 1
        assert stats.error_count == 1

    def test_record_multiple_calls(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("tool_a", 0.1, success=True)
        monitor.record_call("tool_a", 0.2, success=True)
        monitor.record_call("tool_a", 0.3, success=False)
        stats = monitor.get_tool_stats("tool_a")
        assert stats.call_count == 3
        assert stats.error_count == 1
        assert stats.max_latency == 0.3

    def test_should_trip_not_enough_data(self):
        monitor = MCPCircuitBreakerMonitor(min_calls_for_metrics=3)
        monitor.record_call("tool_x", 0.1, success=False)
        monitor.record_call("tool_x", 0.1, success=False)
        should_trip, reason = monitor.should_trip("tool_x")
        assert should_trip is False

    def test_should_trip_high_error_rate(self):
        monitor = MCPCircuitBreakerMonitor(max_error_rate=0.3, min_calls_for_metrics=3)
        monitor.record_call("tool_x", 0.1, success=True)
        monitor.record_call("tool_x", 0.1, success=False)
        monitor.record_call("tool_x", 0.1, success=False)
        monitor.record_call("tool_x", 0.1, success=False)
        should_trip, reason = monitor.should_trip("tool_x")
        assert should_trip is True
        assert "error_rate" in reason

    def test_should_trip_high_latency(self):
        monitor = MCPCircuitBreakerMonitor(max_avg_latency_ms=100.0, min_calls_for_metrics=3)
        monitor.record_call("tool_y", 0.05, success=True)
        monitor.record_call("tool_y", 0.05, success=True)
        monitor.record_call("tool_y", 0.15, success=True)  # max_latency=0.15 > 0.1
        should_trip, reason = monitor.should_trip("tool_y")
        assert should_trip is True
        assert "latency" in reason or "max_latency" in reason

    def test_no_trip_within_thresholds(self):
        monitor = MCPCircuitBreakerMonitor(max_error_rate=0.5, min_calls_for_metrics=3)
        monitor.record_call("tool_z", 0.1, success=True)
        monitor.record_call("tool_z", 0.1, success=False)
        monitor.record_call("tool_z", 0.1, success=True)
        should_trip, reason = monitor.should_trip("tool_z")
        assert should_trip is False
        assert reason == ""

    def test_get_all_stats(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("a", 0.1, success=True)
        monitor.record_call("b", 0.2, success=False)
        all_stats = monitor.get_all_stats()
        assert len(all_stats) == 2
        assert "a" in all_stats
        assert "b" in all_stats

    def test_reset_tool(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("tool_x", 0.1, success=True)
        monitor.reset_tool("tool_x")
        assert monitor.get_tool_stats("tool_x") is None

    def test_reset_all(self):
        monitor = MCPCircuitBreakerMonitor()
        monitor.record_call("a", 0.1, success=True)
        monitor.record_call("b", 0.2, success=False)
        monitor.reset_all()
        assert len(monitor.get_all_stats()) == 0


class TestMCPGovernanceCBCheck:
    def test_cb_monitor_trips_in_evaluate(self):
        gov = MCPGovernance()
        # Record enough errors to trip the CB monitor
        for _ in range(5):
            gov.cb_monitor.record_call("failing_tool", 0.1, success=False)

        result = gov.evaluate(tool_name="failing_tool", agent_id="agent-001")
        assert result.verdict == MCPDecisionVerdict.DENY
        assert "circuit_breaker_monitor" in result.matched_rule

    def test_cb_monitor_allows_within_threshold(self):
        gov = MCPGovernance()
        # Record successful calls - use a tool name that's not dangerous
        for _ in range(5):
            gov.cb_monitor.record_call("read_file", 0.1, success=True)

        result = gov.evaluate(tool_name="read_file", agent_id="agent-001")
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_client_checks_cb_state_before_call(self):
        client = MCPClient()
        gov = MCPGovernance()
        # Trip the CB
        cb = gov.circuit_breaker
        for _ in range(cb._max_failures):
            cb.record_failure()
        assert cb.is_open

        client.register_governance(gov)
        mock_transport = MockTransport()
        conn = MCPConnection(
            transport=mock_transport,
            config_hash="test-hash",
            state=ConnectionState.CONNECTED,
            session_id="test-session",
        )

        result = client.call_tool(
            conn=conn,
            tool_name="read_file",
            args={},
            agent_id="agent-001",
        )
        assert result.is_error
        assert result.error_code == -32002
        assert "Circuit breaker is open" in (result.error or {}).get("message", "")

    def test_client_tracks_latency_in_cb_monitor(self):
        client = MCPClient()
        gov = MCPGovernance()
        client.register_governance(gov)

        mock_transport = MockTransport()
        conn = MCPConnection(
            transport=mock_transport,
            config_hash="test-hash",
            state=ConnectionState.CONNECTED,
            session_id="test-session",
        )
        client._connections["test"] = conn

        result = client.call_tool(
            conn=conn,
            tool_name="read_file",
            args={},
            agent_id="agent-001",
        )
        assert result is not None
        stats = gov.cb_monitor.get_tool_stats("read_file")
        assert stats is not None
        assert stats.call_count >= 1

    def test_cb_monitor_custom_config(self):
        monitor = MCPCircuitBreakerMonitor(
            max_error_rate=0.1, max_avg_latency_ms=500.0, min_calls_for_metrics=2
        )
        gov = MCPGovernance(cb_monitor=monitor)
        assert gov.cb_monitor is monitor

    def test_cb_audit_summary_includes_monitor_stats(self):
        gov = MCPGovernance()
        gov.cb_monitor.record_call("tool_a", 0.1, success=True)
        gov.cb_monitor.record_call("tool_b", 0.2, success=False)
        gov.evaluate(tool_name="read_file", agent_id="agent-001")

        summary = gov.get_audit_summary()
        assert summary["cb_monitored_tools"] == 2
        assert "tool_a" in summary["cb_monitor_tool_stats"]
        assert "tool_b" in summary["cb_monitor_tool_stats"]
        assert summary["cb_monitor_tool_stats"]["tool_a"]["call_count"] == 1
        assert summary["cb_monitor_tool_stats"]["tool_b"]["error_count"] == 1


# ============================================================================
# E1.3: Audit Log HMAC Enhancement
# ============================================================================


class TestMCPGovernanceAuditEnhanced:
    def test_get_audit_entry_valid(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        entry = gov.get_audit_entry(0)
        assert entry is not None
        assert entry.tool_name == "read_file"

    def test_get_audit_entry_invalid(self):
        gov = MCPGovernance()
        assert gov.get_audit_entry(0) is None
        assert gov.get_audit_entry(-1) is None

    def test_clear_audit_log(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")
        assert len(gov.get_audit_log()) == 2

        cleared = gov.clear_audit_log()
        assert cleared == 2
        assert len(gov.get_audit_log()) == 0

    def test_verify_audit_integrity_clean(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")
        violations = gov.verify_audit_integrity()
        assert len(violations) == 0

    def test_verify_audit_integrity_detects_tamper(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        # Tamper with the audit log entry
        if gov._audit_log:
            gov._audit_log[0].tool_name = "write_file"
        violations = gov.verify_audit_integrity()
        assert len(violations) >= 1
        assert violations[0]["issue"] == "signature_mismatch"

    def test_export_audit_log_syslog_format(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="read_file", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")

        exported = gov.export_audit_log(format="syslog")
        assert "MAREF-MCP-GOV" in exported
        assert "read_file" in exported
        assert "write_file" in exported
        lines = exported.split("\n")
        assert len(lines) == 2

    def test_export_audit_log_invalid_format(self):
        gov = MCPGovernance()
        try:
            gov.export_audit_log(format="invalid")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Unsupported" in str(e)


# ============================================================================
# E1.4: HITL Flow Enhancement
# ============================================================================


class TestMCPGovernanceHITLEnhanced:
    def test_get_hitl_events_all(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="shell_exec", agent_id="agent-001")
        gov.evaluate(tool_name="write_file", agent_id="agent-001")

        events = gov.get_hitl_events()
        assert len(events) >= 2

    def test_get_hitl_events_filter_by_status(self):
        gov = MCPGovernance()
        result = gov.evaluate(tool_name="shell_exec", agent_id="agent-001")
        assert result.hitl_event_id is not None

        # Approve one event
        gov.approve_tool_call(result.hitl_event_id, "human")

        approved = gov.get_hitl_events(status="approved")
        assert len(approved) >= 1
        assert approved[0]["event_id"] == result.hitl_event_id

    def test_get_hitl_event_by_id(self):
        gov = MCPGovernance()
        result = gov.evaluate(tool_name="shell_exec", agent_id="agent-001")

        event = gov.get_hitl_event(result.hitl_event_id)
        assert event is not None
        assert event["event_id"] == result.hitl_event_id

    def test_get_hitl_event_not_found(self):
        gov = MCPGovernance()
        event = gov.get_hitl_event("nonexistent-id")
        assert event is None

    def test_check_hitl_timeouts_no_pending(self):
        hitl = HITLRouter()
        gov = MCPGovernance(hitl_router=hitl)
        auto_approved = gov.check_hitl_timeouts()
        assert len(auto_approved) == 0

    def test_hitl_audit_summary_includes_pending(self):
        gov = MCPGovernance()
        gov.evaluate(tool_name="shell_exec", agent_id="agent-001")
        summary = gov.get_audit_summary()
        assert summary["hitl_pending"] >= 1


# ============================================================================
# E1.5: Policy Mapping Table
# ============================================================================


class TestMCPPolicyMapping:
    def test_default_mapping(self):
        mapping = MCPPolicyMapping.default()
        assert mapping.get_rule_for_tool("ping") == "mcp-rule-001"
        assert mapping.get_rule_for_tool("read_file") == "mcp-rule-002"
        assert mapping.get_rule_for_tool("shell") == "mcp-rule-003"
        assert mapping.get_rule_for_tool("bash") == "mcp-rule-003"
        assert mapping.get_rule_for_tool("write_file") == "mcp-rule-005"
        assert mapping.get_rule_for_tool("unknown_tool") == "mcp-rule-006"

    def test_from_yaml(self):
        yaml_str = """
version: "1.0"
mappings:
  - tools: ["custom_tool"]
    rule: "custom-rule"
  - patterns: ["*"]
    rule: "fallback-rule"
"""
        mapping = MCPPolicyMapping.from_yaml(yaml_str)
        assert mapping.get_rule_for_tool("custom_tool") == "custom-rule"
        assert mapping.get_rule_for_tool("anything_else") == "fallback-rule"

    def test_from_yaml_missing_mappings(self):
        try:
            MCPPolicyMapping.from_yaml("version: '1.0'\n")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "mappings" in str(e)

    def test_from_yaml_file(self):
        yaml_str = """
version: "1.0"
mappings:
  - tools: ["file_tool"]
    rule: "file-rule"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_str)
            tmp_path = f.name

        try:
            mapping = MCPPolicyMapping.from_yaml_file(tmp_path)
            assert mapping.get_rule_for_tool("file_tool") == "file-rule"
        finally:
            os.unlink(tmp_path)

    def test_pattern_matching_prefix(self):
        mapping = MCPPolicyMapping(
            mappings=[
                {"patterns": ["read_"], "rule": "read-rule"},
                {"patterns": ["*"], "rule": "default-rule"},
            ]
        )
        assert mapping.get_rule_for_tool("read_file") == "read-rule"
        assert mapping.get_rule_for_tool("read_data") == "read-rule"
        assert mapping.get_rule_for_tool("write_file") == "default-rule"

    def test_pattern_matching_suffix(self):
        mapping = MCPPolicyMapping(
            mappings=[
                {"patterns": ["_tool"], "rule": "tool-rule"},
                {"patterns": ["*"], "rule": "default-rule"},
            ]
        )
        assert mapping.get_rule_for_tool("my_tool") == "tool-rule"
        assert mapping.get_rule_for_tool("something") == "default-rule"

    def test_pattern_matching_substring(self):
        mapping = MCPPolicyMapping(
            mappings=[
                {"patterns": ["danger"], "rule": "danger-rule"},
                {"patterns": ["*"], "rule": "default-rule"},
            ]
        )
        assert mapping.get_rule_for_tool("super_dangerous_tool") == "danger-rule"
        assert mapping.get_rule_for_tool("safe_tool") == "default-rule"

    def test_to_yaml(self):
        mapping = MCPPolicyMapping(
            mappings=[
                {"tools": ["a"], "rule": "rule-1"},
                {"patterns": ["*"], "rule": "rule-2"},
            ]
        )
        yaml_out = mapping.to_yaml()
        assert "rule-1" in yaml_out
        assert "rule-2" in yaml_out
        # Round-trip
        mapping2 = MCPPolicyMapping.from_yaml(yaml_out)
        assert mapping2.get_rule_for_tool("a") == "rule-1"

    def test_custom_yaml_structure(self):
        yaml_str = """
version: "1.0"
mappings:
  - tools: ["git_push", "git_commit"]
    rule: "mcp-rule-005"
  - tools: ["git_log", "git_status"]
    rule: "mcp-rule-002"
  - patterns: ["git_*"]
    rule: "mcp-rule-006"
"""
        mapping = MCPPolicyMapping.from_yaml(yaml_str)
        assert mapping.get_rule_for_tool("git_push") == "mcp-rule-005"
        assert mapping.get_rule_for_tool("git_log") == "mcp-rule-002"
        assert mapping.get_rule_for_tool("git_rebase") == "mcp-rule-006"


class TestMCPMappedPolicyEngine:
    def test_default_mapping_engine(self):
        engine = MCPMappedPolicyEngine()
        assert engine.mapping is not None
        assert engine.mapping.get_rule_for_tool("ping") == "mcp-rule-001"

    def test_mapped_evaluate_protocol_signal(self):
        engine = MCPMappedPolicyEngine()
        ctx = MCPPolicyContext(tool_name="ping")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_mapped_evaluate_dangerous_tool(self):
        engine = MCPMappedPolicyEngine()
        ctx = MCPPolicyContext(tool_name="shell")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_mapped_evaluate_write_tool(self):
        engine = MCPMappedPolicyEngine()
        ctx = MCPPolicyContext(tool_name="write_file")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ASK_USER

    def test_mapped_evaluate_fallback(self):
        engine = MCPMappedPolicyEngine()
        ctx = MCPPolicyContext(tool_name="completely_unknown", trust_level=MCPTrustLevel.TRUSTED)
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_set_mapping(self):
        engine = MCPMappedPolicyEngine()
        custom_mapping = MCPPolicyMapping(
            mappings=[
                {"tools": ["custom_tool"], "rule": "mcp-rule-001"},
                {"patterns": ["*"], "rule": "mcp-rule-006"},
            ]
        )
        engine.set_mapping(custom_mapping)
        ctx = MCPPolicyContext(tool_name="custom_tool")
        result = engine.evaluate(ctx)
        assert result.verdict == MCPDecisionVerdict.ALLOW

    def test_mapped_engine_in_governance(self):
        mapping = MCPPolicyMapping(
            mappings=[
                {"tools": ["safe_read"], "rule": "mcp-rule-002"},
                {"patterns": ["*"], "rule": "mcp-rule-006"},
            ]
        )
        engine = MCPMappedPolicyEngine(mapping=mapping)
        gov = MCPGovernance(policy_engine=engine)

        result = gov.evaluate(tool_name="safe_read", agent_id="agent-001")
        assert result.verdict == MCPDecisionVerdict.ALLOW

        result2 = gov.evaluate(tool_name="bash", agent_id="agent-001")
        assert (
            result2.verdict == MCPDecisionVerdict.DENY
        )  # TrustLevelBasedGate denies untrusted shell
