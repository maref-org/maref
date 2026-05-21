"""End-to-end tests for the PERCV-MAREF integration closed loop.

These tests verify the complete integration pipeline without requiring
actual LLM calls or the PERCV package at runtime — all external
dependencies are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv import (
    CardBridge,
    CostMonitor,
    PERCVGatewayAdapter as GatewayAdapter,
    GatewayRole,
    PERCVConfig,
    PERCVPipelineAdapter as PipelineAdapter,
    PipelineDirective,
    VerificationBridge,
)


@pytest.fixture
def mock_gateway() -> MagicMock:
    gw = MagicMock()
    gw.chat.return_value.content = "mock response"
    gw.chat.return_value.cost_cny = 0.001
    gw.chat.return_value.latency_ms = 100.0
    gw.chat.return_value.provider = "siliconflow"

    resp_a = MagicMock()
    resp_a.content = "Model A result"
    resp_b = MagicMock()
    resp_b.content = "Model B result"
    gw.chat_with_verification.return_value = (resp_a, resp_b)

    gw.get_budget_status.return_value = {
        "monthly_budget": 5000.0,
        "spent": 1500.0,
        "pct_used": 30.0,
    }
    gw.get_monthly_cost.return_value = 1500.0
    gw.is_over_budget.return_value = False
    return gw


class TestClosedLoop:
    """End-to-end verification of the PERCV-MAREF integration."""

    def test_config_integration(self) -> None:
        config = PERCVConfig(
            percv_package_path="/fake/path",
            vault_path="test_vault",
            monthly_budget_cny=3000.0,
        )
        assert config.monthly_budget_cny == 3000.0
        assert config.enable_cost_monitor
        assert config.enable_hitl_gate
        assert config.governance_state_on_failure == "STABILIZE"
        assert config.ratchet_budget == 20

    def test_gateway_cost_monitor_integration(self, mock_gateway: MagicMock) -> None:
        monitor = CostMonitor(gateway_adapter=mock_gateway)
        status = monitor.check_and_act()
        assert status["alert"] == "ok"
        assert status["monthly_cost"] == 1500.0

        mock_gateway.get_budget_status.return_value["pct_used"] = 85.0
        status2 = monitor.check_and_act()
        assert status2["alert"] == "warning"

    def test_gateway_pipeline_roles(self, mock_gateway: MagicMock) -> None:
        adapter = GatewayAdapter(router=MagicMock(), cost_tracker=MagicMock())
        for role in GatewayRole:
            assert role.value in adapter._model_mapping

    def test_pipeline_card_bridge_flow(self) -> None:
        pipeline = PipelineAdapter()
        assert pipeline._error_policy == "degrade"
        assert pipeline._results == []

        bridge = CardBridge()
        assert bridge.get_synced_count() == 0

    def test_verification_protocols_mocked(self, mock_gateway: MagicMock) -> None:
        bridge = VerificationBridge(gateway_adapter=mock_gateway)

        kdp_results = bridge.run_protocol_a([{"claim": "Revenue grew 20%"}])
        assert len(kdp_results) >= 1

        hypothesis_result = bridge.run_protocol_c({
            "linked_kdps": ["K-001"],
            "assumptions": [{"text": "a1"}],
            "core_forecast": "If A then B",
        })
        assert hypothesis_result.protocol == "C"

    def test_full_pipeline_directive_flow(self) -> None:
        sm = MagicMock()
        sm.current_state.value = 1

        adapter = PipelineAdapter(governance_state_machine=sm)

        assert adapter._determine_directive("step1", True, None) == PipelineDirective.CONTINUE
        assert adapter._determine_directive("step2", False, "error") == PipelineDirective.RETRY

        sm.current_state.value = 5
        assert adapter._determine_directive("step3", False, "error") == PipelineDirective.DEGRADE

        sm.current_state.value = 9
        assert adapter._determine_directive("step4", False, "error") == PipelineDirective.HALT

    def test_gateway_maref_router_integration(self, mock_gateway: MagicMock) -> None:
        from maref.integration.gateway import GatewayRouter
        from maref.governance.types import GovernanceState

        router = GatewayRouter(percv_adapter=mock_gateway)
        decision = router.compute_route(
            state=GovernanceState.ANALYZE,
            entropy=2,
        )
        assert decision.state == "ANALYZE"
        assert decision.route.value in ("cheap", "standard", "capable", "deterministic", "fallback")

    def test_all_adapters_importable(self) -> None:
        from maref.integration.percv import (
            PERCVConfig,
            PERCVGatewayAdapter,
            GatewayResponse,
            GatewayRole,
            PERCVPipelineAdapter,
            PipelineDirective,
            CardBridge,
            CostMonitor,
            RatchetBridge,
            VerificationBridge,
        )
        assert PERCVGatewayAdapter is not None
        assert GatewayResponse is not None
        assert GatewayRole is not None
        assert PERCVPipelineAdapter is not None
        assert PipelineDirective is not None
        assert CardBridge is not None
        assert CostMonitor is not None
        assert RatchetBridge is not None
        assert VerificationBridge is not None
        assert PERCVConfig is not None
