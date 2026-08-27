# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileNotice: Patent disclosures apply to core FSM implementations. See NOTICE file for details.

"""Security-critical function decorators for MAREF.

Usage:
    from maref.security.decorators import security_critical, set_audit_context

    @security_critical
    def handle_sensitive_operation(...) -> ...:
        ...

    # 在审计流程中启用审计记录收集
    entries = []
    set_audit_context(entries)
    try:
        handle_sensitive_operation(...)
    finally:
        set_audit_context(None)
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)

_audit_context: contextvars.ContextVar[list[dict[str, str]] | None] = contextvars.ContextVar(
    "_maref_audit_context", default=None
)


def set_audit_context(entries: list[dict[str, str]] | None) -> None:
    """设置审计上下文。传入列表收集记录，传 None 清除。"""
    _audit_context.set(entries)


def _try_audit_log(func_name: str, args: tuple, kwargs: dict, event: str, error: str | None = None) -> None:
    """尝试写入审计上下文。无活跃上下文时静默跳过。"""
    ctx = _audit_context.get()
    if ctx is None:
        return
    param_str = repr(args[:3]) + repr(sorted(kwargs.items()))
    param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
    entry: dict[str, str] = {
        "event": f"SECURITY_CRITICAL_{event}",
        "function": func_name,
        "param_hash": param_hash,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if error:
        entry["error"] = error[:200]
    ctx.append(entry)


def security_critical(func: F) -> F:
    """Mark a function as security-critical.

    Logs entry/exit at DEBUG level and records the call in any active
    audit context (via set_audit_context). This decorator is mandatory
    for all functions that handle authentication, authorization,
    cryptography, or cross-domain trust decisions per MAREF project rules.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("SECURITY_ENTER: %s", func.__qualname__)
        _try_audit_log(func.__qualname__, args, kwargs, "ENTER")
        try:
            result = func(*args, **kwargs)
            logger.debug("SECURITY_EXIT: %s", func.__qualname__)
            _try_audit_log(func.__qualname__, args, kwargs, "EXIT")
            return result
        except Exception as exc:
            logger.warning("SECURITY_EXCEPTION in %s: %s", func.__qualname__, exc)
            _try_audit_log(func.__qualname__, args, kwargs, "EXCEPTION", str(exc))
            raise

    wrapper._maref_security_critical = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
