from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CostMonitor:
    """Feeds PERCV LLM cost tracking into MAREF governance.

    Monitors monthly LLM API spend through PERCV's CostTracker and
    triggers MAREF governance actions when thresholds are crossed:

    - Warning (80%): Log alert, suggest model downgrade
    - Critical (95%): Trip circuit breaker, force cheap models
    - Exceeded (100%): HALT all LLM-dependent operations

    Usage:
        monitor = CostMonitor(gateway_adapter=adapter, circuit_breaker=cb)
        status = monitor.check_and_act()
    """

    def __init__(
        self,
        config: Any | None = None,
        gateway_adapter: Any | None = None,
        circuit_breaker: Any | None = None,
        governance_manager: Any | None = None,
        state_machine: Any | None = None,  # deprecated, use governance_manager
        warning_pct: float = 80.0,
        critical_pct: float = 95.0,
    ):
        self._config = config
        self._gateway = gateway_adapter

        # Use config values if provided
        if config and hasattr(config, "monthly_budget_cny"):
            self._monthly_budget = config.monthly_budget_cny
        else:
            self._monthly_budget = 5000.0

        self._cb = circuit_breaker
        # Use governance_manager if provided, fallback to state_machine for backwards compatibility
        self._governance_manager = governance_manager or state_machine
        self._warning_pct = warning_pct
        self._critical_pct = critical_pct
        self._last_check_result: dict[str, Any] = {}

    def check_and_act(self) -> dict[str, Any]:
        """Check current LLM spend and trigger governance actions if needed.

        Returns a status dict with alert level and current metrics.
        """
        if self._gateway is None:
            return {"alert": "error", "error": "gateway adapter not configured"}
        try:
            budget_status = self._gateway.get_budget_status()
        except Exception as exc:
            logger.error("Failed to get budget status: %s", exc)
            return {"alert": "error", "error": str(exc)}

        spent = budget_status.get("spent", 0.0)
        budget = budget_status.get("monthly_budget", 5000.0)
        pct_used = budget_status.get("pct_used", 0.0)

        result: dict[str, Any] = {
            "alert": "ok",
            "monthly_cost": spent,
            "budget": budget,
            "pct_used": pct_used,
            "actions_taken": [],
        }

        if pct_used >= 100.0:
            result["alert"] = "exceeded"
            result["actions_taken"].append("budget_exceeded")
            if self._cb and hasattr(self._cb, "trip"):
                self._cb.trip(
                    reason=f"LLM budget exceeded: ¥{spent:.0f} > ¥{budget:.0f}",
                )
            if self._governance_manager:
                try:
                    from maref.governance.types import GovernanceState

                    self._governance_manager.transition(
                        GovernanceState.HALT,
                        reason=f"cost_budget_exceeded:{spent:.0f}",
                    )
                except Exception as exc:
                    logger.warning("State transition failed: %s", exc)

        elif pct_used >= self._critical_pct:
            result["alert"] = "critical"
            result["actions_taken"].append("budget_critical")
            if self._cb and hasattr(self._cb, "trip"):
                self._cb.trip(
                    reason=f"LLM budget critical: {pct_used:.0f}% used (¥{spent:.0f})",
                )

        elif pct_used >= self._warning_pct:
            result["alert"] = "warning"
            result["actions_taken"].append("budget_warning")
            logger.warning(
                "LLM budget warning: %.0f%% used (¥%.0f / ¥%.0f)",
                pct_used,
                spent,
                budget,
            )

        self._last_check_result = result
        return result

    def should_downgrade_model(self) -> bool:
        """Whether budget pressure recommends cheaper model selection."""
        return self._last_check_result.get("pct_used", 0) >= self._warning_pct

    def get_status(self) -> dict[str, Any]:
        """Return the most recent check result."""
        return self._last_check_result or {"alert": "never_checked"}

    def reset_monthly(self) -> None:
        """Reset the monitored state (called at month boundary)."""
        self._last_check_result = {}
        logger.info("CostMonitor reset for new month")
