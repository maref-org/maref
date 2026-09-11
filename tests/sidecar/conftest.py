"""Shared fixtures for sidecar tests.

Sidecar 的有状态端点（/api/providers 等 POST 注册）写模块级 dict
（sidecar.server._providers/_skills/_tasks/_sessions 等）。若不清理，
一个测试 POST 注册的 provider 会残留，后续测试（如
test_providers_have_models 遍历 providers 要求含 models）顺序相关失败。
autouse fixture 在每个测试后把模块级状态恢复为首次快照。
"""

from __future__ import annotations

import copy

import pytest

import sidecar.server as server

_STATE_DICTS = (
    "_providers",
    "_skills",
    "_tasks",
    "_sessions",
    "_compliance_agents",
    "_compliance_audit_logs",
)
_baseline: dict[str, dict] | None = None


@pytest.fixture(autouse=True)
def _restore_sidecar_state():
    global _baseline
    if _baseline is None:
        _baseline = {
            name: copy.deepcopy(getattr(server, name)) for name in _STATE_DICTS
        }
    yield
    for name in _STATE_DICTS:
        current = getattr(server, name)
        base = _baseline[name]
        current.clear()
        current.update(copy.deepcopy(base))
