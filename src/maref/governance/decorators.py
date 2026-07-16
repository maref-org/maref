"""@governed decorator — auto-injection governance for any Python function.

Usage:
    @governed(require="file.write")
    def save_file(path, content):
        ...

    @governed(pipeline=custom_pipeline, require="shell.exec")
    def run_command(cmd):
        ...
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
    Verdict,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class GovernanceDenied(Exception):
    """Raised when @governed decorator blocks an action."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__(f"Governance denied: {reason}")


_default_pipeline: GovernancePipeline | None = None


def set_default_pipeline(pipeline: GovernancePipeline) -> None:
    """Set the default GovernancePipeline for all @governed decorators."""
    global _default_pipeline
    _default_pipeline = pipeline
    logger.info("Default governance pipeline set: %s", type(pipeline).__name__)


def get_default_pipeline() -> GovernancePipeline | None:
    """Get the default GovernancePipeline."""
    return _default_pipeline


def governed(
    require: str = "",
    action: str | None = None,
    pipeline: GovernancePipeline | None = None,
    agent_id: str = "decorated",
    tenant_id: str = "default",
) -> Callable[[F], F]:
    """Decorator that automatically applies governance checks.

    Args:
        require: Action name to govern (e.g. "file.write", "shell.exec").
        action: Alias for require (prefer require).
        pipeline: GovernancePipeline to use. Falls back to global default.
        agent_id: Agent identifier for governance logging.
        tenant_id: Tenant identifier for governance routing.

    Raises:
        GovernanceDenied: If governance verdict is DENY.

    Example:
        @governed(require="file.write")
        def save(path, content): ...
    """
    action_name = require or action or ""
    if not action_name:
        raise ValueError("governed() requires a 'require' or 'action' argument")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal pipeline
            if pipeline is None:
                pipeline = _default_pipeline
            if pipeline is None:
                logger.warning(
                    "No governance pipeline set for @governed(%s) on %s — allowing",
                    action_name, func.__qualname__,
                )
                return func(*args, **kwargs)

            request = GovernanceRequest(
                action=action_name,
                agent_id=agent_id,
                tenant_id=tenant_id,
            )
            result = pipeline.govern(request)

            if result.verdict == Verdict.DENY:
                raise GovernanceDenied(result.reason)

            if result.verdict == Verdict.ASK_USER:
                event = result.hitl_event_id
                logger.info(
                    "HITL requested for %s on %s (event=%s)",
                    action_name, func.__qualname__, event,
                )

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
