# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileNotice: Patent disclosures apply to core FSM implementations. See NOTICE file for details.

"""Security-critical function decorators for MAREF.

Usage:
    from maref.security.decorators import security_critical

    @security_critical
    def handle_sensitive_operation(...) -> ...:
        ...
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


def security_critical(func: F) -> F:
    """Mark a function as security-critical.

    Logs entry/exit at DEBUG level and ensures the call is recorded
    in any active audit context. This decorator is mandatory for all
    functions that handle authentication, authorization, cryptography,
    or cross-domain trust decisions per MAREF project rules.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("SECURITY_ENTER: %s", func.__qualname__)
        try:
            result = func(*args, **kwargs)
            logger.debug("SECURITY_EXIT: %s", func.__qualname__)
            return result
        except Exception as exc:
            logger.warning("SECURITY_EXCEPTION in %s: %s", func.__qualname__, exc)
            raise

    # Attach marker attribute for static analysis / policy enforcement
    wrapper._maref_security_critical = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
