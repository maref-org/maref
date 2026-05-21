"""MAREF Structured Logging Configuration.

Integrates structlog with OpenTelemetry trace context for correlated
structured log output. Supports development (rich console) and
production (JSON) modes.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

from maref.observability.trace_context import get_current_trace_id

_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _add_trace_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    trace_id = get_current_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def _add_caller_info(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    frame = sys._getframe(6) if sys.version_info >= (3, 11) else sys._getframe(5)
    event_dict["module"] = frame.f_globals.get("__name__", "unknown")
    event_dict["func"] = frame.f_code.co_name
    event_dict["line"] = frame.f_lineno
    return event_dict


def configure_logging(
    *,
    env: str | None = None,
    log_level: str | None = None,
    json_output: bool | None = None,
) -> None:
    """Configure structured logging for MAREF.

    Args:
        env: Environment name ('development', 'production', 'test').
              Defaults to MAREF_ENV env var, then 'development'.
        log_level: Log level string. Defaults to MAREF_LOG_LEVEL env var,
                   then 'INFO'.
        json_output: Force JSON output. Defaults to True in production,
                     False in development.
    """
    env = env or os.environ.get("MAREF_ENV", "development")
    log_level = log_level or os.environ.get("MAREF_LOG_LEVEL", "INFO")
    is_production = env == "production"

    if json_output is None:
        json_output = is_production

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _add_trace_context,
        structlog.processors.TimeStamper(fmt=_TIMESTAMP_FMT, utc=True),
        structlog.dev.ConsoleRenderer() if not json_output else structlog.processors.JSONRenderer(),
    ]

    if not json_output:
        shared_processors.insert(1, _add_caller_info)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            *shared_processors,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr if is_production else sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    if is_production:
        logging.getLogger().handlers.clear()
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
        ))
        logging.getLogger().addHandler(handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger with trace context support.

    Args:
        name: Logger name, typically __name__.

    Returns:
        Configured structlog BoundLogger.
    """
    return structlog.get_logger(name or __name__)
