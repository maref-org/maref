"""Tests for M4 cost health check (INC-2026-08-13-001 / G2)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from maref.observability.meta_monitor import _cost_events_path, _guard_events_path, check_cost


def _write_events(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _cost(model: str, ts: float) -> dict:
    return {"event_type": "cost_event", "timestamp": ts, "model": model,
            "input_chars": 1000, "output_chars": 500, "wall_ms": 100.0, "guard": "none"}


class TestCheckCost:
    def test_no_events_passes_liveness_warns(self, tmp_path: Path) -> None:
        res = check_cost(cost_events_path=tmp_path / "missing.json",
                         guard_events_path=tmp_path / "missing2.json")
        # 无事件 → telemetry_liveness fail，其余通过
        assert res["passed"] is False
        assert res["checks"]["telemetry_liveness"]["passed"] is False

    def test_high_cost_model_over_limit_critical(self, tmp_path: Path) -> None:
        now = time.time()
        events = [_cost("glm-5.2", now - i * 10) for i in range(70)]
        p = tmp_path / "cost.jsonl"
        _write_events(p, events)
        res = check_cost(cost_events_path=p, guard_events_path=tmp_path / "g.jsonl",
                         high_cost_hourly_limit=60)
        assert res["passed"] is False
        assert res["checks"]["high_cost_model_calls"]["passed"] is False
        assert res["checks"]["high_cost_model_calls"]["detail"]["glm-5.2"] > 60

    def test_low_cost_model_high_volume_ok(self, tmp_path: Path) -> None:
        now = time.time()
        events = [_cost("deepseek-v4-flash", now - i * 5) for i in range(200)]
        p = tmp_path / "cost.jsonl"
        _write_events(p, events)
        res = check_cost(cost_events_path=p, guard_events_path=tmp_path / "g.jsonl",
                         high_cost_hourly_limit=60)
        # 便宜模型不算 critical，但 telemetry_liveness 通过
        assert res["checks"]["high_cost_model_calls"]["passed"] is True
        assert res["checks"]["telemetry_liveness"]["passed"] is True

    def test_guard_block_rate_warning(self, tmp_path: Path) -> None:
        now = time.time()
        events = [_cost("deepseek-v4-flash", now - i) for i in range(10)]
        p = tmp_path / "cost.jsonl"
        _write_events(p, events)
        guards = [{"event_type": "guard_block", "timestamp": now, "model": "glm-5.2",
                   "reason": "call_guard", "detail": "x"} for _ in range(60)]
        gp = tmp_path / "guard.jsonl"
        _write_events(gp, guards)
        res = check_cost(cost_events_path=p, guard_events_path=gp)
        assert res["checks"]["guard_block_rate"]["passed"] is False
        assert res["checks"]["guard_block_rate"]["guarded_24h"] == 60

    def test_stale_events_ignored(self, tmp_path: Path) -> None:
        old = time.time() - 90000  # >24h
        events = [_cost("glm-5.2", old) for _ in range(100)]
        p = tmp_path / "cost.jsonl"
        _write_events(p, events)
        res = check_cost(cost_events_path=p, guard_events_path=tmp_path / "g.jsonl")
        assert res["checks"]["telemetry_liveness"]["passed"] is False
        assert res["total_events_24h"] == 0

    def test_default_paths_are_under_maref_audit(self) -> None:
        assert str(_cost_events_path()).endswith("cost_events.ndjson")
        assert str(_guard_events_path()).endswith("guard_blocks.ndjson")
