from __future__ import annotations

import json
from http.server import HTTPServer
from threading import Thread

import pytest

from sidecar.exfiltration_probe import (
    DataExfiltrationProbe,
    ExfiltrationAlert,
    ExfiltrationMode,
    ExfiltrationSeverity,
)
from sidecar.mcp_bridge import (
    SIDECAR_MCP_RESOURCES,
    SIDECAR_MCP_TOOLS,
    SidecarMCPBridge,
)

# ─── DataExfiltrationProbe Tests ─────────────────────────────


class TestDataExfiltrationProbe:
    def test_init_defaults(self):
        probe = DataExfiltrationProbe()
        assert probe.baseline_volume == 1000.0
        assert probe.volume_stddev == 200.0
        assert probe.max_consecutive_skip == 2
        assert len(probe.get_alerts()) == 0

    def test_check_cross_border_tier0_cn(self):
        probe = DataExfiltrationProbe()
        result = probe.check_cross_border(data_tier=0, jurisdiction="CN", provider="deepseek")
        assert result is None
        assert probe.get_alert_count() == 0

    def test_check_cross_border_tier1_us(self):
        probe = DataExfiltrationProbe()
        result = probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL
        assert result.mode == ExfiltrationMode.CROSS_BORDER
        assert "Tier 1" in result.message
        assert probe.get_alert_count(ExfiltrationSeverity.CRITICAL) == 1

    def test_check_cross_border_tier1_us_nvidia(self):
        probe = DataExfiltrationProbe()
        result = probe.check_cross_border(data_tier=2, jurisdiction="US", provider="nvidia-us")
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL

    def test_check_github_exposure_private(self):
        probe = DataExfiltrationProbe()
        result = probe.check_github_exposure(
            remote_url="git@github.com:user/repo.git",
            visibility="private",
            paths=[".env"],
        )
        assert result is None

    def test_check_github_exposure_public_sensitive(self):
        probe = DataExfiltrationProbe()
        result = probe.check_github_exposure(
            remote_url="https://github.com/user/repo.git",
            visibility="public",
            paths=["src/main.py", ".env", "config/credentials.json"],
        )
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL
        assert result.mode == ExfiltrationMode.GITHUB_EXPOSURE
        assert ".env" in str(result.details.get("matched_paths", []))

    def test_check_github_exposure_public_safe(self):
        probe = DataExfiltrationProbe()
        result = probe.check_github_exposure(
            remote_url="https://github.com/user/repo.git",
            visibility="public",
            paths=["README.md", "src/main.py"],
        )
        assert result is None

    def test_check_volume_anomaly_normal(self):
        probe = DataExfiltrationProbe(baseline_volume=1000, volume_stddev=200)
        result = probe.check_volume_anomaly(current_volume=1100)
        assert result is None

    def test_check_volume_anomaly_warning(self):
        probe = DataExfiltrationProbe(baseline_volume=1000, volume_stddev=200)
        result = probe.check_volume_anomaly(current_volume=1700)
        assert result is not None
        assert result.severity == ExfiltrationSeverity.WARNING

    def test_check_volume_anomaly_critical(self):
        probe = DataExfiltrationProbe(baseline_volume=1000, volume_stddev=200)
        result = probe.check_volume_anomaly(current_volume=2500)
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL

    def test_check_fragment_reconstruction_safe(self):
        probe = DataExfiltrationProbe()
        result = probe.check_fragment_reconstruction(
            fragment_providers=["deepseek", "siliconflow", "baidu"]
        )
        assert result is None

    def test_check_fragment_reconstruction_violation(self):
        probe = DataExfiltrationProbe()
        result = probe.check_fragment_reconstruction(
            fragment_providers=["deepseek", "siliconflow", "deepseek"]
        )
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL
        assert result.mode == ExfiltrationMode.FRAGMENT_RECONSTRUCTION

    def test_check_semantic_bypass_normal(self):
        probe = DataExfiltrationProbe(max_consecutive_skip=2)
        result = probe.check_semantic_bypass(consecutive_skip_count=0)
        assert result is None
        result = probe.check_semantic_bypass(consecutive_skip_count=1)
        assert result is None
        result = probe.check_semantic_bypass(consecutive_skip_count=2)
        assert result is None

    def test_check_semantic_bypass_violation(self):
        probe = DataExfiltrationProbe(max_consecutive_skip=2)
        result = probe.check_semantic_bypass(consecutive_skip_count=3)
        assert result is not None
        assert result.severity == ExfiltrationSeverity.CRITICAL
        assert result.mode == ExfiltrationMode.SEMANTIC_BYPASS

    def test_check_all_multiple_alerts(self):
        probe = DataExfiltrationProbe(baseline_volume=1000, volume_stddev=200)
        alerts = probe.check_all(
            data_tier=1,
            jurisdiction="US",
            provider="openai",
            current_volume=2500,
        )
        assert len(alerts) >= 1

    def test_get_alerts_by_severity(self):
        probe = DataExfiltrationProbe(baseline_volume=1000, volume_stddev=200)
        probe.check_all(data_tier=1, jurisdiction="US", provider="openai")
        critical_alerts = probe.get_alerts(severity=ExfiltrationSeverity.CRITICAL)
        assert len(critical_alerts) >= 1

    def test_get_alerts_by_mode(self):
        probe = DataExfiltrationProbe()
        probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        mode_alerts = probe.get_alerts(mode=ExfiltrationMode.CROSS_BORDER)
        assert len(mode_alerts) >= 1

    def test_clear_alerts(self):
        probe = DataExfiltrationProbe()
        probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        assert probe.get_alert_count() > 0
        probe.clear_alerts()
        assert probe.get_alert_count() == 0

    def test_alert_callback(self):
        captured: list[ExfiltrationAlert] = []

        def callback(alert: ExfiltrationAlert) -> None:
            captured.append(alert)

        probe = DataExfiltrationProbe(alert_callback=callback)
        probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        assert len(captured) == 1
        assert captured[0].mode == ExfiltrationMode.CROSS_BORDER

    def test_alert_id_uniqueness(self):
        probe = DataExfiltrationProbe()
        a1 = probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        probe.clear_alerts()
        a2 = probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        assert a1 is not None and a2 is not None
        assert a1.alert_id != a2.alert_id

    def test_alert_to_dict(self):
        probe = DataExfiltrationProbe()
        alert = probe.check_cross_border(data_tier=1, jurisdiction="US", provider="openai")
        assert alert is not None
        d = alert.to_dict()
        assert d["mode"] == "cross_border"
        assert d["severity"] == "CRITICAL"
        assert "alert_id" in d
        assert "details" in d


# ─── SidecarMCPBridge Governance Tools Tests ─────────────────


class TestGovernanceToolsRegistration:
    def test_tool_count(self):
        governance_tools = [t for t in SIDECAR_MCP_TOOLS if t.name.startswith("maref_")]
        assert len(governance_tools) >= 11

    def test_ingest_signal_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_ingest_signal" in names

    def test_check_exfiltration_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_check_exfiltration" in names

    def test_pre_route_check_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_pre_route_check" in names

    def test_post_route_audit_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_post_route_audit" in names

    def test_update_trust_score_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_update_trust_score" in names

    def test_trigger_playbook_tool_defined(self):
        names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_trigger_playbook" in names

    def test_resource_count(self):
        assert len(SIDECAR_MCP_RESOURCES) >= 8

    def test_new_resources_defined(self):
        uris = [r["uri"] for r in SIDECAR_MCP_RESOURCES]
        assert "maref://signals/{signal_type}" in uris
        assert "maref://governance/exfiltration/alerts" in uris
        assert "maref://governance/drift/metrics" in uris
        assert "maref://governance/trust-scores" in uris

    def test_tool_definitions_have_schemas(self):
        for tool in SIDECAR_MCP_TOOLS:
            assert "inputSchema" in tool.to_dict() or "input_schema" in tool.__dict__


class TestGovernanceToolsExecution:
    def test_ingest_signal(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_ingest_signal", {
            "signal_type": "PROVIDER_CALL",
            "payload": {"provider": "deepseek", "tier": 0, "tokens": 1500},
            "source": "test",
        })
        assert result is not None
        content = json.loads(result["content"][0]["text"])
        assert content["ingested"] is True
        assert content["signal_type"] == "PROVIDER_CALL"

    def test_ingest_signal_triggers_exfiltration_on_tier_violation(self):
        bridge = SidecarMCPBridge()
        # DATA_TIER_VIOLATION with US provider should trigger exfiltration check
        result = bridge.handle_tool_call("maref_ingest_signal", {
            "signal_type": "DATA_TIER_VIOLATION",
            "payload": {"tier": 2, "jurisdiction": "US", "provider": "openai"},
            "source": "test",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["ingested"] is True

    def test_check_exfiltration_no_alerts(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_check_exfiltration", {
            "data_tier": 0,
            "jurisdiction": "CN",
            "provider": "deepseek",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["alerts_raised"] == 0

    def test_check_exfiltration_with_cross_border_alert(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_check_exfiltration", {
            "data_tier": 2,
            "jurisdiction": "US",
            "provider": "openai",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["alerts_raised"] >= 1
        assert content["critical_count"] >= 1

    def test_pre_route_check_low_risk(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_pre_route_check", {
            "agent_id": "default/worker-1",
            "tier": 0,
            "impact_level": 1,
        })
        content = json.loads(result["content"][0]["text"])
        assert content["allowed"] is True

    def test_pre_route_check_high_risk(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_pre_route_check", {
            "agent_id": "default/worker-1",
            "tier": 2,
            "impact_level": 6,
        })
        content = json.loads(result["content"][0]["text"])
        # H_c = 2*0.3 + 6*0.12 = 0.6 + 0.72 = 1.32 → capped at 1.0 → >0.8
        assert content["allowed"] is False
        assert content["recommended_action"] == "escalate_to_governance"

    def test_post_route_audit_no_drift(self):
        bridge = SidecarMCPBridge()
        decision = {"provider": "deepseek", "tier": 0, "channel": "fast"}
        result = bridge.handle_tool_call("maref_post_route_audit", {
            "route_decision": decision,
            "actual_execution": dict(decision),
        })
        content = json.loads(result["content"][0]["text"])
        assert content["drift_detected"] is False
        assert content["drift_fields"] == 0

    def test_post_route_audit_with_drift(self):
        bridge = SidecarMCPBridge()
        decision = {"provider": "deepseek", "tier": 0, "channel": "fast"}
        actual = {"provider": "openai", "tier": 0, "channel": "fast"}
        result = bridge.handle_tool_call("maref_post_route_audit", {
            "route_decision": decision,
            "actual_execution": actual,
        })
        content = json.loads(result["content"][0]["text"])
        assert content["drift_detected"] is True
        assert content["drift_fields"] >= 1

    def test_update_trust_score_positive(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_update_trust_score", {
            "agent_id": "default/worker-1",
            "score_delta": 0.1,
            "reason": "Good behavior",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["agent_id"] == "default/worker-1"
        assert content["previous_score"] == 1.0
        assert content["new_score"] == 1.0  # capped at 1.0

    def test_update_trust_score_negative(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_update_trust_score", {
            "agent_id": "default/worker-1",
            "score_delta": -0.3,
            "reason": "Policy violation",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["new_score"] == 0.7

    def test_trigger_playbook_exfiltration(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_trigger_playbook", {
            "alert_type": "exfiltration",
            "context": {"provider": "openai", "tier": 2},
            "severity": "CRITICAL",
        })
        content = json.loads(result["content"][0]["text"])
        assert content["playbook_triggered"] is True
        assert "isolate_affected_provider" in content["steps"]

    def test_trigger_playbook_drift(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_trigger_playbook", {
            "alert_type": "drift",
            "context": {},
        })
        content = json.loads(result["content"][0]["text"])
        assert content["playbook_triggered"] is True
        assert "compare_decision_vs_execution" in content["steps"]

    def test_trigger_playbook_violation(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_trigger_playbook", {
            "alert_type": "violation",
            "context": {},
        })
        content = json.loads(result["content"][0]["text"])
        assert content["playbook_triggered"] is True
        assert "halt_current_request_chain" in content["steps"]

    def test_unknown_tool_returns_error(self):
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_nonexistent", {})
        assert result.get("isError") is True

    def test_bridge_list_tools(self):
        bridge = SidecarMCPBridge()
        tools = bridge.list_tools()
        names = [t["name"] for t in tools]
        assert "maref_ingest_signal" in names
        assert "maref_check_exfiltration" in names
        assert "maref_pre_route_check" in names
        assert "maref_post_route_audit" in names
        assert "maref_update_trust_score" in names
        assert "maref_trigger_playbook" in names
        assert len(tools) >= 11

    def test_bridge_list_resources(self):
        bridge = SidecarMCPBridge()
        resources = bridge.list_resources()
        uris = [r["uri"] for r in resources]
        assert "maref://signals/{signal_type}" in uris
        assert "maref://governance/exfiltration/alerts" in uris

    def test_bridge_server_info_version(self):
        bridge = SidecarMCPBridge()
        info = bridge.get_server_info()
        assert info["serverInfo"]["version"] == "0.27.0"
        assert info["serverInfo"]["name"] == "MAREF Sidecar"

    def test_bridge_capabilities(self):
        bridge = SidecarMCPBridge()
        caps = bridge.get_capabilities()
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps


# ─── __main__ Server Creation Tests ──────────────────────────


class TestMainServer:
    def test_create_server(self):
        from maref.__main__ import create_server
        server = create_server(port=18941)
        assert server.name == "maref-governance-mcp"
        assert len(server._tools) >= 11

    def test_mcp_handler_POST_not_found(self):
        from maref.__main__ import create_server
        server = create_server()
        from maref.integration.mcp_transport import JSONRPCRequest
        from maref.integration.mcp_security import MCPTrustLevel

        req = JSONRPCRequest(method="nonexistent", params={}, id=1)
        resp = server.handle_request(req, trust_level=MCPTrustLevel.TRUSTED)
        assert resp.is_error

    def test_mcp_handler_tools_list(self):
        from maref.__main__ import create_server
        server = create_server()
        from maref.integration.mcp_transport import JSONRPCRequest
        from maref.integration.mcp_security import MCPTrustLevel

        req = JSONRPCRequest(method="tools/list", params={}, id=1)
        resp = server.handle_request(req, trust_level=MCPTrustLevel.TRUSTED)
        assert not resp.is_error
        assert resp.result is not None
        assert len(resp.result["tools"]) >= 11

    def test_mcp_handler_tools_call_ingest_signal(self):
        from maref.__main__ import create_server
        server = create_server()
        from maref.integration.mcp_transport import JSONRPCRequest
        from maref.integration.mcp_security import MCPTrustLevel

        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "maref_ingest_signal",
                "arguments": {
                    "signal_type": "PROVIDER_CALL",
                    "payload": {"provider": "test", "tokens": 100},
                    "source": "test",
                },
            },
            id=1,
        )
        resp = server.handle_request(req, trust_level=MCPTrustLevel.TRUSTED)
        assert not resp.is_error
        assert resp.result["content"][0]["text"] is not None
