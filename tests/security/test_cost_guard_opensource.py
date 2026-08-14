"""Tests for the open-source self-contained CostGuard (INC-2026-08-13-001).

These tests run against src/maref/cost_guard.py (open-source), NOT the
closed-source unified_proxy. They stay green in CI even when
~/.claude/scripts/unified_proxy.py is absent.

Covers: call guard (sliding window), ctx guard, daily token budget,
HMAC audit writes (cost_event / guard_block), usage aggregation.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from maref.cost_guard import CostGuard


@pytest.fixture
def guard(tmp_path: Path) -> CostGuard:
    # 隔离：审计目录 → tmp_path/audit，配置 → tmp_path/proxy_config.json
    os.environ["UP_AUDIT_DIR"] = str(tmp_path / "audit")
    os.environ["UP_CONFIG"] = str(tmp_path / "proxy_config.json")
    os.environ["MAREF_HMAC_SECRET_KEY"] = "test-key-123"
    cfg = {
        "call_hard_limit": 3,
        "call_soft_limit": 10,
        "ctx_limit_chars": 500,
        "daily_token_budget": 100,
    }
    (tmp_path / "proxy_config.json").write_text(json.dumps(cfg))
    g = CostGuard()
    yield g
    os.environ.pop("UP_AUDIT_DIR", None)
    os.environ.pop("UP_CONFIG", None)
    os.environ.pop("MAREF_HMAC_SECRET_KEY", None)


class TestCallGuard:
    def test_blocks_over_hard_limit(self, guard: CostGuard) -> None:
        for i in range(3):
            lim, blocked = guard.enforce_call("glm-5.2")
            assert blocked is False and lim == 3, f"call {i} should pass"
        lim, blocked = guard.enforce_call("glm-5.2")
        assert blocked is True and lim == 3

    def test_soft_limit_for_cheap_model(self, guard: CostGuard) -> None:
        for i in range(10):
            lim, blocked = guard.enforce_call("deepseek-v4-flash")
            assert blocked is False and lim == 10, f"call {i} should pass"
        _, blocked = guard.enforce_call("deepseek-v4-flash")
        assert blocked is True

    def test_window_slides(self, guard: CostGuard) -> None:
        now = time.time()
        with guard._lock:
            guard._call_windows["glm-5.2"] = [now - 2000, now - 1900, now - 1850]
        lim, blocked = guard.enforce_call("glm-5.2", now=now)
        assert blocked is False  # 旧记录全部滑出，hard_limit=3 未满


class TestCtxGuard:
    def test_estimate_req_chars(self) -> None:
        body = {
            "messages": [
                {"content": "a" * 100},
                {"content": [{"type": "text", "text": "b" * 50}]},
            ]
        }
        assert CostGuard.estimate_req_chars(body) == 150

    def test_ctx_limit_blocks(self, guard: CostGuard) -> None:
        assert guard.enforce_ctx(600) is True   # > 500
        assert guard.enforce_ctx(500) is False  # == 500 边界放行
        assert guard.enforce_ctx(100) is False


class TestDailyBudget:
    def test_budget_blocks_over_limit(self, guard: CostGuard, tmp_path: Path) -> None:
        # 预算 100，预写当日 90 token
        daily = tmp_path / "audit" / "daily_tokens.json"
        daily.parent.mkdir(parents=True, exist_ok=True)
        daily.write_text(json.dumps({"day": time.strftime("%Y-%m-%d"), "total": 90}))
        guard._budget_day = ""
        # 90 + 30 = 120 > 100 → blocked
        assert guard.enforce_budget(30) is True
        assert guard.enforce_budget(5) is False  # 90 + 5 = 95 <= 100

    def test_budget_resets_next_day(self, guard: CostGuard, tmp_path: Path) -> None:
        daily = tmp_path / "audit" / "daily_tokens.json"
        daily.parent.mkdir(parents=True, exist_ok=True)
        daily.write_text(json.dumps({"day": "2026-01-01", "total": 9999}))
        guard._budget_day = ""
        assert guard._daily_total() == 0

    def test_record_tokens_accumulates(self, guard: CostGuard) -> None:
        guard.record_tokens(40)
        assert guard._daily_total() == 40
        guard.record_tokens(25)
        assert guard._daily_total() == 65


class TestAuditWrites:
    def test_cost_event_written_with_hmac(self, guard: CostGuard, tmp_path: Path) -> None:
        guard.log_cost_event("glm-5.2", 1000, 500, 12.3, "none")
        path = tmp_path / "audit" / "cost_events.ndjson"
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["event_type"] == "cost_event"
        assert rec["model"] == "glm-5.2"
        assert rec["actor"] == "maref_cost_guard"
        assert len(rec.get("hmac_signature", "")) == 64

    def test_guard_block_written(self, guard: CostGuard, tmp_path: Path) -> None:
        guard.log_guard_block("glm-5.2", "call_guard", "limit=3/30min")
        path = tmp_path / "audit" / "guard_blocks.ndjson"
        rec = json.loads(path.read_text().splitlines()[-1])
        assert rec["event_type"] == "guard_block"
        assert rec["reason"] == "call_guard"
        assert len(rec.get("hmac_signature", "")) == 64

    def test_fail_closed_without_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        monkeypatch.setenv("UP_AUDIT_DIR", str(tmp_path / "audit2"))
        monkeypatch.setenv("UP_CONFIG", str(tmp_path / "proxy_config.json"))
        monkeypatch.setenv("HOME", str(tmp_path))  # 隔离 Path.home()，避免读到真实 ~/.maraf_hmac_key
        monkeypatch.chdir(tmp_path)  # 隔离 cwd 的 .maraf_hmac_key
        g = CostGuard()
        cfg = tmp_path / "proxy_config.json"
        cfg.write_text(json.dumps({"daily_token_budget": 100}))
        g.log_cost_event("glm-5.2", 10, 10, 1.0, "none")
        cost_path = tmp_path / "audit2" / "cost_events.ndjson"
        assert not cost_path.exists()  # fail-closed：不写裸记录


class TestUsageStats:
    def test_usage_aggregates(self, guard: CostGuard, tmp_path: Path) -> None:
        base = tmp_path / "audit"
        now = time.time()

        cost = base / "cost_events.ndjson"
        cost.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for m in ("glm-5.2", "deepseek-v4-flash"):
            lines.append(
                json.dumps({
                    "event_type": "cost_event", "timestamp": now, "model": m,
                    "input_chars": 1000, "output_chars": 100, "wall_ms": 5.0, "guard": "none",
                })
            )
        cost.write_text("\n".join(lines) + "\n", encoding="utf-8")
        guard_p = base / "guard_blocks.ndjson"
        guard_p.write_text(
            json.dumps({
                "event_type": "guard_block", "timestamp": now, "model": "glm-5.2",
                "reason": "call_guard", "detail": "x",
            }) + "\n",
            encoding="utf-8",
        )
        stats = guard.usage_stats()
        assert stats["daily_calls"] == 2
        assert stats["guarded_24h"] == 1
        assert stats["guards"]["call_guard"] == 1
        assert stats["by_model"]["glm-5.2"]["calls"] == 1
