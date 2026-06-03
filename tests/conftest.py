"""Pytest configuration and global fixtures."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

# Mock missing optional dependencies that tests may import
_MISSING_MODULES = [
    "sidecar",
    "sidecar.collector",
    "sidecar.monitor",
    "sidecar.protocol",
    "sidecar.server",
    "sidecar.obs_bridge",
    "sidecar.jsonrpc_bridge",
    "sidecar.mcp_bridge",
    "sidecar.exfiltration_probe",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
    "numpy",
    "fastapi",
    "cryptography",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.x509.oid",
    "Quartz",
    "keyring",
    "transformers",
    "torch",
    "opentelemetry",
    "opentelemetry.trace",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.exporter.otlp.proto.http.metric_exporter",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.sdk.metrics",
    "opentelemetry.sdk.metrics.export",
    "opentelemetry.sdk.resources",
    "click",
    "tomllib",
    "tomli",
    "uvicorn",
    "huggingface_hub",
    "starlette.middleware.base",
    "starlette.requests",
    "starlette.responses",
    "gmssl",
    "percv.schemas",
    "percv.pipeline",
    "percv.agents.scout",
    "percv.gateway.router",
]


def _create_mock_module(name: str) -> ModuleType:
    """Create a mock module where any attribute access returns a MagicMock."""

    class _MockModule(ModuleType):
        def __getattr__(self, item: str) -> MagicMock:
            return MagicMock()

    return _MockModule(name)


for _mod_name in _MISSING_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _create_mock_module(_mod_name)
