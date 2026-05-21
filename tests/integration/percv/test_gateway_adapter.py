"""Tests for GatewayAdapter — PERCV LLM gateway to MAREF bridge."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.gateway_adapter import (
    PERCVGatewayAdapter as GatewayAdapter,
    GatewayResponse,
    GatewayRole,
)


class TestGatewayRole:
    def test_role_values(self) -> None:
        assert GatewayRole.PRIMARY.value == "primary_reasoning"
        assert GatewayRole.LONG_CONTEXT.value == "long_context"
        assert GatewayRole.REASONING.value == "reasoning"


class TestGatewayResponse:
    def test_to_dict(self) -> None:
        resp = GatewayResponse(
            content="test output",
            model_used="sf-deepseek",
            cost_cny=0.002,
            latency_ms=150.0,
            provider="siliconflow",
        )
        d = resp.to_dict()
        assert d["content"] == "test output"
        assert d["model_used"] == "sf-deepseek"
        assert d["cost_cny"] == 0.002
        assert d["error"] is None

    def test_to_dict_with_error(self) -> None:
        resp = GatewayResponse(
            content="", model_used="sf-deepseek", cost_cny=0.0,
            latency_ms=0.0, provider="error", error="timeout",
        )
        assert resp.to_dict()["error"] == "timeout"


class TestGatewayAdapter:
    def test_init_no_router(self) -> None:
        adapter = GatewayAdapter()
        assert adapter._router is None
        assert adapter._cost_tracker is None

    def test_chat_no_percv(self) -> None:
        with patch.dict("sys.modules", {"percv": None, "percv.gateway": None, "percv.gateway.router": None}):
            adapter = GatewayAdapter()
            with pytest.raises(RuntimeError, match="PERCV package is required"):
                adapter.chat([{"role": "user", "content": "hello"}])

    def test_chat_with_router(self) -> None:
        mock_router = MagicMock()
        mock_router.call.return_value = "mock response"

        mock_cost = MagicMock()
        mock_cost.current_month_spent.return_value = 0.05

        adapter = GatewayAdapter(
            router=mock_router,
            cost_tracker=mock_cost,
        )

        resp = adapter.chat(
            messages=[{"role": "user", "content": "analyze"}],
            role=GatewayRole.PRIMARY,
        )

        assert isinstance(resp, GatewayResponse)
        assert "mock" in resp.content
        assert resp.provider in ("sf", "siliconflow")
        mock_router.call.assert_called_once()

    def test_chat_with_system_prompt(self) -> None:
        mock_router = MagicMock()
        mock_router.call.return_value = "system aware response"
        mock_cost = MagicMock()
        mock_cost.current_month_spent.return_value = 0.01

        adapter = GatewayAdapter(router=mock_router, cost_tracker=mock_cost)
        resp = adapter.chat([
            {"role": "system", "content": "You are an expert analyst."},
            {"role": "user", "content": "Analyze market trends."},
        ])

        assert resp.content == "system aware response"
        call_kwargs = mock_router.call.call_args
        assert "expert analyst" in call_kwargs[0][1]

    def test_chat_router_error(self) -> None:
        mock_router = MagicMock()
        mock_router.call.side_effect = RuntimeError("API timeout")
        mock_cost = MagicMock()

        adapter = GatewayAdapter(router=mock_router, cost_tracker=mock_cost)
        resp = adapter.chat([{"role": "user", "content": "test"}])

        assert resp.error is not None
        assert "API timeout" in resp.error

    def test_dual_blind_verification(self) -> None:
        mock_router = MagicMock()
        mock_router.dual_call.return_value = {
            "sf-deepseek": "result A",
            "sf-kimi": "result B",
        }
        mock_cost = MagicMock()
        mock_cost.current_month_spent.return_value = 0.08

        adapter = GatewayAdapter(router=mock_router, cost_tracker=mock_cost)
        resp_a, resp_b = adapter.chat_with_verification(
            [{"role": "user", "content": "verify"}],
            protocol="A",
        )

        assert resp_a.content == "result A"
        assert resp_b.content == "result B"
        mock_router.dual_call.assert_called_once()

    def test_get_monthly_cost(self) -> None:
        mock_cost = MagicMock()
        mock_cost.current_month_spent.return_value = 1234.56
        adapter = GatewayAdapter(
            router=MagicMock(), cost_tracker=mock_cost,
        )
        assert adapter.get_monthly_cost() == 1234.56

    def test_get_monthly_cost_no_tracker(self) -> None:
        adapter = GatewayAdapter()
        assert adapter.get_monthly_cost() == 0.0

    def test_budget_status(self) -> None:
        mock_cost = MagicMock()
        mock_cost.budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 1000.0,
            "remaining": 4000.0,
            "pct_used": 20.0,
            "warning": False,
            "exceeded": False,
        }
        adapter = GatewayAdapter(router=MagicMock(), cost_tracker=mock_cost)
        status = adapter.get_budget_status()
        assert status["spent"] == 1000.0
        assert not status["exceeded"]

    def test_is_over_budget(self) -> None:
        mock_cost = MagicMock()
        mock_cost.is_over_budget.return_value = True
        adapter = GatewayAdapter(router=MagicMock(), cost_tracker=mock_cost)
        assert adapter.is_over_budget()

    def test_get_stats(self) -> None:
        mock_router = MagicMock()
        mock_router.call.return_value = "ok"
        mock_cost = MagicMock()
        mock_cost.current_month_spent.return_value = 50.0

        adapter = GatewayAdapter(router=mock_router, cost_tracker=mock_cost)
        adapter.chat([{"role": "user", "content": "hi"}])
        adapter.chat([{"role": "user", "content": "hi2"}])

        stats = adapter.get_stats()
        assert stats["total_calls"] == 2
        assert stats["errors"] == 0

    def test_get_cost_summary(self) -> None:
        mock_cost = MagicMock()
        mock_cost.summary_by_model.return_value = {
            "sf-deepseek": {"calls": 5, "total_cost": 0.5},
        }
        adapter = GatewayAdapter(router=MagicMock(), cost_tracker=mock_cost)
        summary = adapter.get_cost_summary_by_model()
        assert "sf-deepseek" in summary
