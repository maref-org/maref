"""Tests for maref selfcheck (INC-2026-08-13-001 / G11)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from maref.observability.meta_monitor import check_audit_log_growth, check_audit_noise, check_cost


class TestSelfCheckComponents:
    def test_audit_log_growth_detects_real_events(self, tmp_path: Path) -> None:
        (tmp_path / "audit.jsonl").write_text(json.dumps({
            "event_type": "cost_event", "timestamp": time.time(), "model": "glm-5.2",
        }) + "\n")
        res = check_audit_log_growth(max_age=86400.0, audit_base=tmp_path)
        assert res["passed"] is True

    def test_audit_noise_detects_pollution(self, tmp_path: Path) -> None:
        now = time.time()
        (tmp_path / "governance_audit.jsonl").write_text(
            "\n".join(json.dumps({"event_type": "state_transition", "timestamp": now - i,
                                  "actor": "state_machine"}) for i in range(1500))
        )
        res = check_audit_noise(audit_base=tmp_path, window_hours=24.0)
        assert res["passed"] is False

    def test_check_cost_detects_high_model_spike(self, tmp_path: Path) -> None:
        now = time.time()
        events = [{"event_type": "cost_event", "timestamp": now - i * 10,
                   "model": "glm-5.2", "input_chars": 1000} for i in range(70)]
        p = tmp_path / "cost.jsonl"
        with open(p, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        res = check_cost(cost_events_path=p, guard_events_path=tmp_path / "g.jsonl",
                         high_cost_hourly_limit=60)
        assert res["passed"] is False
        assert res["checks"]["high_cost_model_calls"]["detail"]["glm-5.2"] > 60

    def test_selfcheck_command_registered(self) -> None:
        from maref_lite.cli import app
        commands = {c.name for c in app.registered_commands}
        assert "selfcheck" in commands
        assert "cost-policy" in commands
        assert "usage" in commands
