"""otel_middleware 版本位点回归。

service.version 是 sync_version.py 管理的发布位点，必须与包版本一致；
同时覆盖 tracer 工厂，避免版本改动随发布 PR 降低新增代码覆盖率。
"""

from __future__ import annotations

import pytest

from maref import __version__
from maref.observability import otel_middleware

pytestmark = pytest.mark.skipif(
    not otel_middleware._OTEL_AVAILABLE, reason="opentelemetry extra 未安装"
)


def test_create_resource_uses_package_version():
    resource = otel_middleware._create_resource("maref-test")
    assert resource is not None
    assert resource.attributes["service.version"] == __version__


def test_create_maref_tracer_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert otel_middleware.create_maref_tracer("maref-test") is not None
