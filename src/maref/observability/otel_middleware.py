"""MAREF FastAPI OpenTelemetry Middleware.

Provides automatic tracing and RED metrics collection for all API requests.
Integrates with OpenTelemetry SDK to export traces via OTLP.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from maref.observability.red_metrics import REDMetricsCollector
from maref.observability.trace_context import set_trace_context

_global_red_collector = REDMetricsCollector()

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.trace import (  # type: ignore[import-not-found]
        SpanKind,
        StatusCode,
        format_trace_id,
    )

    _tracer = trace.get_tracer("maref.fastapi", "0.26.0")
    _OTEL_AVAILABLE = True
except ImportError:
    pass

current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)


class OpenTelemetryMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that instruments all HTTP requests with OpenTelemetry tracing.

    Creates spans for each request with:
    - HTTP method, route, status code
    - Request/response duration
    - Error information (if applicable)
    - Trace ID injected into response headers for frontend correlation
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _OTEL_AVAILABLE:
            return await call_next(request)

        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        span_name = f"{method} {path}"

        with _tracer.start_as_current_span(
            span_name,
            kind=SpanKind.SERVER,
            attributes={
                "http.method": method,
                "http.url": str(request.url),
                "http.target": path,
                "http.client_ip": client_host,
                "http.user_agent": request.headers.get("user-agent", ""),
            },
        ) as span:
            start_time = time.perf_counter()

            trace_id = format_trace_id(span.get_span_context().trace_id)
            current_trace_id.set(trace_id)
            set_trace_context(trace_id)

            try:
                response = await call_next(request)
                duration_ms = (time.perf_counter() - start_time) * 1000

                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.duration_ms", round(duration_ms, 2))
                span.set_attribute("maref.trace_id", trace_id)

                _global_red_collector.record_request(
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

                if 400 <= response.status_code < 500:
                    span.set_status(StatusCode.OK, "Client error")
                elif response.status_code >= 500:
                    span.set_status(StatusCode.ERROR, "Server error")

                response.headers["X-Trace-ID"] = trace_id
                response.headers["X-Request-Duration-Ms"] = str(round(duration_ms, 2))

                return response

            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("http.duration_ms", round(duration_ms, 2))
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__name__)

                _global_red_collector.record_request(
                    path=path,
                    method=method,
                    status_code=500,
                    duration_ms=duration_ms,
                )
                raise


class DesktopOperationSpanMixin:
    """Mixin class for wrapping Desktop Controller operations with OTel spans.

    Usage:
        class DesktopController(DesktopOperationSpanMixin):
            def execute_operation(self, op):
                return self._trace_operation("execute_operation", {"op_type": op.op_type.value})
                    .with_logic(super().execute_operation, op)
    """

    def _create_operation_span(
        self, operation_name: str, attributes: dict[str, Any] | None = None
    ) -> _SpanContextManager:
        return _SpanContextManager(
            operation_name,
            attributes=attributes or {},
        )


class _SpanContextManager:
    """Helper to create OTel spans for desktop operations."""

    def __init__(self, operation_name: str, attributes: dict[str, Any] | None = None) -> None:
        self._operation_name = operation_name
        self._attributes = attributes or {}
        self._span = None

    def __enter__(self) -> _SpanContextManager:
        if _OTEL_AVAILABLE:
            self._span = _tracer.start_span(
                f"maref.desktop.{self._operation_name}",
                attributes={
                    "maref.operation": self._operation_name,
                    **self._attributes,
                },
            )
            trace_id = format_trace_id(self._span.get_span_context().trace_id)  # type: ignore[attr-defined]
            current_trace_id.set(trace_id)
            set_trace_context(trace_id)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is not None:
            if exc_val is not None:
                self._span.set_status(StatusCode.ERROR, str(exc_val))
                self._span.record_exception(exc_val)
                self._span.set_attribute("error.type", type(exc_val).__name__)
            else:
                self._span.set_status(StatusCode.OK)
            self._span.end()


def create_maref_tracer(
    service_name: str = "maref-desktop",
    otlp_endpoint: str | None = None,
) -> Any:
    """Create and configure a MAREF-specific OTel tracer.

    Args:
        service_name: OTel service name for trace identification.
        otlp_endpoint: OTLP exporter endpoint. If None, uses OTEL_EXPORTER_OTLP_ENDPOINT env var.

    Returns:
        Configured tracer instance.
    """
    import os

    if not _OTEL_AVAILABLE:
        return None

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
        )
        from opentelemetry.trace import set_tracer_provider

        provider = TracerProvider(resource=_create_resource(service_name))
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        set_tracer_provider(provider)

    return trace.get_tracer("maref", "0.26.0")


def _create_resource(service_name: str) -> Any:
    """Create OTel resource with service metadata."""
    try:
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]

        return Resource.create(
            {
                "service.name": service_name,
                "service.version": "0.26.0",
                "telemetry.sdk.name": "maref",
            }
        )
    except Exception:
        return None
