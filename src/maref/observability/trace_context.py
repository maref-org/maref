"""MAREF Trace Context Management.

Provides utilities for propagating trace IDs across service boundaries
(Frontend → Backend → Sidecar → Governance Layer).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
current_span_id: ContextVar[str | None] = ContextVar("current_span_id", default=None)
trace_context: ContextVar[dict[str, Any]] = ContextVar("trace_context", default=None)  # type: ignore[arg-type]


def get_current_trace_id() -> str | None:
    """Get the current trace ID from context."""
    return current_trace_id.get()


def get_current_span_id() -> str | None:
    """Get the current span ID from context."""
    return current_span_id.get()


def set_trace_context(
    trace_id: str | None = None, span_id: str | None = None, **kwargs: Any
) -> None:
    """Set trace context for the current execution flow.

    Args:
        trace_id: OpenTelemetry trace ID.
        span_id: OpenTelemetry span ID.
        **kwargs: Additional context attributes to store.
    """
    if trace_id is not None:
        current_trace_id.set(trace_id)
    if span_id is not None:
        current_span_id.set(span_id)

    ctx = (trace_context.get() or {}).copy()
    ctx.update(kwargs)
    trace_context.set(ctx)


def get_trace_context() -> dict[str, Any]:
    """Get the current trace context as a dictionary."""
    ctx = (trace_context.get() or {}).copy()
    tid = get_current_trace_id()
    sid = get_current_span_id()
    if tid:
        ctx["trace_id"] = tid
    if sid:
        ctx["span_id"] = sid
    return ctx


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Inject trace context into HTTP headers for downstream propagation.

    Args:
        headers: Existing HTTP headers dictionary.

    Returns:
        Updated headers with trace context injected.
    """
    headers = headers.copy()
    trace_id = get_current_trace_id()
    if trace_id:
        headers["X-Trace-ID"] = trace_id

    span_id = get_current_span_id()
    if span_id:
        headers["X-Span-ID"] = span_id

    return headers


def extract_trace_context(headers: dict[str, str]) -> None:
    """Extract trace context from incoming HTTP headers.

    Args:
        headers: HTTP headers dictionary containing trace context.
    """
    trace_id = headers.get("X-Trace-ID") or headers.get("x-trace-id")
    span_id = headers.get("X-Span-ID") or headers.get("x-span-id")
    set_trace_context(trace_id=trace_id, span_id=span_id)


def clear_trace_context() -> None:
    """Clear the current trace context."""
    current_trace_id.set(None)
    current_span_id.set(None)
    trace_context.set({})
