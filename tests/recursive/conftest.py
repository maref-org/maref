"""Shared fixtures for recursive tests.

desktop/gui_build/playwright 是环境相关 heavy probe：真实 measure 在无
pnpm/桌面/浏览器的 CI 上会把正常快照误判为 CRITICAL/WARNING。递归域
诊断测试(r1/r2/r3)须跨环境确定——此 autouse fixture 统一 mock 这些
probe 的 measure 并重置 BaseProbe 类级 TTL 缓存。

类级缓存重置是必须的：BaseProbe._measure_cached 用类级 _cached_reading/
_cached_at(6h TTL)，先前测试(真实或 mock)填充的 CRITICAL 值会短路后续
mock 的 measure。fixture setup+teardown 都重置，防双向泄漏。
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.observation.probes import (
    DesktopProbe,
    GUIBuildProbe,
    PlaywrightProbe,
    ProbeReading,
    ProbeSeverity,
)

_HEAVY_PROBE_CLASSES = (PlaywrightProbe, DesktopProbe, GUIBuildProbe)


def _normal_reading(name: str) -> ProbeReading:
    return ProbeReading(
        probe_name=name,
        severity=ProbeSeverity.NORMAL,
        value=1.0,
        threshold=0.3,
    )


@pytest.fixture(autouse=True)
def _isolate_heavy_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock env-heavy probes 为 NORMAL + 重置类级 TTL 缓存。

    适用 recursive 域诊断/自愈测试：真实 heavy probe 依赖 pnpm/桌面/
    playwright 等运行环境, 在 CI 上使诊断误判。替换 measure 为返回
    NORMAL 的闭包(实例绑定需 self 参数), 并清空类级缓存使 mock 生效。
    """

    for cls, name in (
        (PlaywrightProbe, "playwright"),
        (DesktopProbe, "desktop"),
        (GUIBuildProbe, "gui_build"),
    ):
        monkeypatch.setattr(
            f"maref.observation.probes.{cls.__name__}.measure",
            _make_normal_measure(name),
        )

    def _reset_cache() -> None:
        for cls in _HEAVY_PROBE_CLASSES:
            cls._cached_reading = None  # type: ignore[attr-defined]
            cls._cached_at = 0.0  # type: ignore[attr-defined]

    _reset_cache()
    yield
    _reset_cache()


def _make_normal_measure(name: str) -> Any:
    def _measure(self: object, context: dict[str, Any] | None = None) -> ProbeReading:
        return _normal_reading(name)

    return _measure


__all__ = ["_isolate_heavy_probes"]
