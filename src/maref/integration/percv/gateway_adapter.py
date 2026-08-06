from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from maref.governance.types import GovernanceState

logger = logging.getLogger(__name__)


class GatewayRole(Enum):
    """Role classification for LLM model selection.

    Maps to PERCV's ModelRole enum values for seamless bridging.
    """

    PRIMARY = "primary_reasoning"
    LONG_CONTEXT = "long_context"
    STRUCTURED = "structured"
    CN_INDUSTRY = "cn_industry"
    GLOBAL = "global"
    REASONING = "reasoning"


@dataclass
class GatewayResponse:
    """Standardized response from a gateway LLM call."""

    content: str
    model_used: str
    cost_cny: float
    latency_ms: float
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model_used": self.model_used,
            "cost_cny": self.cost_cny,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "error": self.error,
        }


_STATE_TO_PURPOSE: dict[GovernanceState, str] = {
    GovernanceState.INIT: "system_init",
    GovernanceState.OBSERVE: "observation",
    GovernanceState.ANALYZE: "analysis",
    GovernanceState.EVALUATE: "evaluation",
    GovernanceState.DECIDE: "decision",
    GovernanceState.ACT: "action",
    GovernanceState.VERIFY: "verification",
    GovernanceState.STABILIZE: "stabilization",
    GovernanceState.REPORT: "reporting",
    GovernanceState.HALT: "halt",
}


class PERCVGatewayAdapter:
    """Wraps PERCV's LLM gateway for MAREF consumption.

    Provides:
    - Role-based model selection mapped from PERCV ModelSpec
    - Cost tracking via PERCV's SQLite-backed CostTracker
    - Automatic failover between providers
    - Budget enforcement (hard cap)
    - 4 verification protocols (dual-blind, adversarial, causal, fact)

    Usage:
        adapter = GatewayAdapter()
        response = adapter.chat(
            messages=[{"role": "user", "content": "Analyze..."}],
            role=GatewayRole.PRIMARY,
        )
    """

    def __init__(
        self,
        config: Any | None = None,
        router: Any = None,
        cost_tracker: Any = None,
        monthly_budget_cny: float = 5000.0,
        model_mapping: dict[str, str] | None = None,
    ):
        self._config = config

        # Use config values if provided
        if config and hasattr(config, "preferred_models"):
            self._model_mapping = config.preferred_models
        else:
            self._model_mapping = model_mapping or {
                GatewayRole.PRIMARY.value: "sf-deepseek",
                GatewayRole.LONG_CONTEXT.value: "sf-kimi",
                GatewayRole.STRUCTURED.value: "oll-llama3",
                GatewayRole.CN_INDUSTRY.value: "sf-qwen",
                GatewayRole.GLOBAL.value: "sf-global",
                GatewayRole.REASONING.value: "sf-deepseek-r1",
            }

        if config and hasattr(config, "monthly_budget_cny"):
            self._monthly_budget = config.monthly_budget_cny
        else:
            self._monthly_budget = monthly_budget_cny

        self._router = router
        self._cost_tracker = cost_tracker
        self._call_history: list[GatewayResponse] = []

    def _ensure_router(self) -> Any:
        if self._router is not None:
            return self._router
        try:
            from percv.gateway.router import (
                CostTracker as _CostTracker,
            )
            from percv.gateway.router import LLMRouter

            if self._cost_tracker is None:
                self._cost_tracker = _CostTracker(monthly_budget=self._monthly_budget)
            self._router = LLMRouter(cost_tracker=self._cost_tracker)
            return self._router
        except ImportError:
            raise RuntimeError(
                "PERCV package is required for GatewayAdapter. "
                "Install with: pip install percv  or  uv add percv"
            ) from None

    def chat(
        self,
        messages: list[dict],
        role: GatewayRole = GatewayRole.PRIMARY,
        temperature: float = 0.7,
        timeout_ms: int = 60000,
        governance_state: GovernanceState | None = None,
    ) -> GatewayResponse:
        """Route a chat completion through PERCV's gateway.

        Args:
            messages: OpenAI-format message list.
            role: Which model role to use (determines model selection).
            temperature: Sampling temperature.
            timeout_ms: HTTP request timeout in milliseconds.
            governance_state: Optional MAREF state for purpose tagging.

        Returns:
            GatewayResponse with content, cost, and metadata.
        """
        router = self._ensure_router()
        model_key = self._model_mapping.get(role.value, "sf-deepseek")

        system_parts: list[str] = []
        user_parts: list[str] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            else:
                user_parts.append(msg.get("content", ""))

        system_prompt = "\n".join(system_parts)
        user_prompt = "\n".join(user_parts)

        purpose = "maref_inference"
        if governance_state:
            purpose = _STATE_TO_PURPOSE.get(governance_state, "maref_inference")

        import time

        t0 = time.perf_counter()
        try:
            content = router.call(model_key, system_prompt, user_prompt, purpose=purpose)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            cost = self._cost_tracker.current_month_spent() if self._cost_tracker else 0.0

            provider_name = self._resolve_provider_name(model_key)
            response = GatewayResponse(
                content=content,
                model_used=model_key,
                cost_cny=round(cost, 4),
                latency_ms=round(elapsed_ms, 1),
                provider=provider_name,
                error=None,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            response = GatewayResponse(
                content="",
                model_used=model_key,
                cost_cny=0.0,
                latency_ms=round(elapsed_ms, 1),
                provider="error",
                error=str(exc),
            )

        self._call_history.append(response)
        return response

    def chat_with_verification(
        self,
        messages: list[dict],
        protocol: str,
        role: GatewayRole = GatewayRole.PRIMARY,
        **kwargs: Any,
    ) -> tuple[GatewayResponse, GatewayResponse]:
        """Run a two-model verification protocol.

        Args:
            messages: Input messages for both models.
            protocol: One of "A" (dual-blind), "B" (adversarial),
                      "C" (causal), "D" (fact-triangulation).
            role: Base role for model selection.

        Returns:
            Tuple of (primary_response, secondary_response).
        """
        router = self._ensure_router()
        model_a = self._model_mapping.get(role.value, "sf-deepseek")
        model_b_map = {
            "A": "sf-kimi",
            "B": "sf-deepseek",
            "C": "sf-qwen",
            "D": "sf-kimi",
        }
        model_b = model_b_map.get(protocol, "sf-kimi")

        system_parts: list[str] = []
        user_parts: list[str] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            else:
                user_parts.append(msg.get("content", ""))
        system_prompt = "\n".join(system_parts)
        user_prompt = "\n".join(user_parts)

        import time

        t0 = time.perf_counter()
        try:
            result = router.dual_call(
                model_a=model_a,
                model_b=model_b,
                prompt_a=system_prompt,
                prompt_b=system_prompt,
                user_input=user_prompt,
                purpose=f"verification_protocol_{protocol}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            cost = self._cost_tracker.current_month_spent() if self._cost_tracker else 0.0

            resp_a = GatewayResponse(
                content=result.get(model_a, ""),
                model_used=model_a,
                cost_cny=round(cost / 2, 4),
                latency_ms=round(elapsed_ms, 1),
                provider="verification",
            )
            resp_b = GatewayResponse(
                content=result.get(model_b, ""),
                model_used=model_b,
                cost_cny=round(cost / 2, 4),
                latency_ms=round(elapsed_ms, 1),
                provider="verification",
            )
            return resp_a, resp_b
        except Exception as exc:
            err_resp = GatewayResponse(
                content="",
                model_used="error",
                cost_cny=0.0,
                latency_ms=0.0,
                provider="error",
                error=str(exc),
            )
            return err_resp, err_resp

    def get_monthly_cost(self) -> float:
        """Return current month's total LLM spend in CNY."""
        if self._cost_tracker:
            return self._cost_tracker.current_month_spent()
        return 0.0

    def get_budget_status(self) -> dict[str, Any]:
        """Return budget status dict with spend, remaining, and warnings."""
        if self._cost_tracker:
            return self._cost_tracker.budget_status()
        return {
            "monthly_budget": self._monthly_budget,
            "spent": 0.0,
            "remaining": self._monthly_budget,
            "pct_used": 0.0,
            "warning": False,
            "exceeded": False,
        }

    def is_over_budget(self) -> bool:
        """Check if monthly budget has been exceeded."""
        if self._cost_tracker:
            return self._cost_tracker.is_over_budget()
        return False

    def get_cost_summary_by_model(self) -> dict[str, Any]:
        """Return per-model cost summary for the current month."""
        if self._cost_tracker:
            return self._cost_tracker.summary_by_model()
        return {}

    def _resolve_provider_name(self, model_key: str) -> str:
        """Resolve provider name for a model key without importing percv at call time."""
        try:
            from percv.gateway.router import MODELS

            spec = MODELS.get(model_key)
            return spec.provider if spec else "unknown"
        except ImportError:
            return model_key.split("-")[0] if "-" in model_key else "unknown"

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate stats for this adapter instance."""
        total_calls = len(self._call_history)
        errors = sum(1 for r in self._call_history if r.error)
        avg_latency = (
            sum(r.latency_ms for r in self._call_history) / total_calls if total_calls > 0 else 0.0
        )
        return {
            "total_calls": total_calls,
            "errors": errors,
            "error_rate": round(errors / total_calls, 3) if total_calls > 0 else 0.0,
            "avg_latency_ms": round(avg_latency, 1),
            "monthly_cost_cny": round(self.get_monthly_cost(), 2),
        }

    async def get_status(self) -> dict[str, Any]:
        """Get the operational status of the gateway adapter.

        Returns:
            Dictionary with status information.
        """
        try:
            router = self._ensure_router()
            if router:
                return {
                    "status": "active",
                    "router_available": True,
                    "budget_status": self.get_budget_status(),
                    "stats": self.get_stats(),
                }
            else:
                return {
                    "status": "fallback",
                    "router_available": False,
                    "message": "PERCV router not available, using fallback",
                    "stats": self.get_stats(),
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "budget_status": self.get_budget_status(),
                "stats": self.get_stats(),
            }

    async def get_providers(self) -> dict[str, Any]:
        """Get available LLM providers.

        Returns:
            Dictionary with provider information.
        """
        try:
            router = self._ensure_router()
            if router and hasattr(router, "get_providers"):
                providers = await router.get_providers()
                return {
                    "available": True,
                    "providers": providers,
                    "count": len(providers) if providers else 0,
                }
            else:
                # Return fallback providers
                return {
                    "available": False,
                    "providers": list(self._model_mapping.values()),
                    "count": len(self._model_mapping),
                    "message": "Using fallback model mapping",
                }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "providers": list(self._model_mapping.values()),
                "count": len(self._model_mapping),
                "message": "Error getting providers, using fallback",
            }
