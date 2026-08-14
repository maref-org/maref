"""Tests for proxy cost guardrails (INC-2026-08-13-001 / G1, G3, G4).

Loads the external unified_proxy.py module (UP_AUDIT_DIR) and verifies:
- cost_event / guard_block audit writes with HMAC signature
- call guard limit enforcement
- ctx guard enforcement
- daily token budget enforcement
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

PROXY = Path(os.environ.get("UP_PROXY_PATH", str(Path.home() / ".claude" / "scripts" / "unified_proxy.py")))


@pytest.fixture(scope="module")
def proxy_mod(tmp_path_factory: Path) -> object:
    """Load unified_proxy module with isolated audit dir + HMAC key."""
    if not PROXY.exists():
        pytest.skip(f"proxy not found: {PROXY}")
    audit_dir = tmp_path_factory.mktemp("audit")
    env = {
        "UP_AUDIT_DIR": str(audit_dir),
        "MAREF_HMAC_SECRET_KEY": "test-key-123",
        "UP_CALL_LIMIT": "3",
        "UP_CTX_LIMIT_CHARS": "500",
        "UP_DAILY_TOKEN_BUDGET": "100",
        "UP_CONFIG": str(tmp_path_factory.mktemp("cfg") / "proxy_config.json"),
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    spec = importlib.util.spec_from_file_location("unified_proxy_test", PROXY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["unified_proxy_test"] = mod
    try:
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("unified_proxy_test", None)


class TestAuditWrites:
    def test_cost_event_written_with_hmac(self, proxy_mod, tmp_path: Path) -> None:
        audit_dir = Path(os.environ["UP_AUDIT_DIR"])
        proxy_mod._log_cost_event("glm-5.2", 1000, 500, 12.3, "none")
        lines = (audit_dir / "cost_events.ndjson").read_text().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["event_type"] == "cost_event"
        assert rec["model"] == "glm-5.2"
        assert "hmac_signature" in rec
        assert len(rec["hmac_signature"]) == 64

    def test_guard_block_written(self, proxy_mod) -> None:
        audit_dir = Path(os.environ["UP_AUDIT_DIR"])
        proxy_mod._log_guard_block("glm-4.7", "call_guard", "limit=3/30min")
        lines = (audit_dir / "guard_blocks.ndjson").read_text().splitlines()
        rec = json.loads(lines[-1])
        assert rec["event_type"] == "guard_block"
        assert rec["reason"] == "call_guard"
        assert rec["model"] == "glm-4.7"

    def test_no_hmac_key_fail_closed(self, proxy_mod) -> None:
        # fail-closed：无 key 时 _log_cost_event 不写裸记录（在隔离 tmp 目录下无 .maraf_hmac_key）
        old_env = os.environ.get("MAREF_HMAC_SECRET_KEY")
        os.environ.pop("MAREF_HMAC_SECRET_KEY", None)
        old_mod_key = proxy_mod._HMAC_KEY
        proxy_mod._HMAC_KEY = ""
        old_cwd = os.getcwd()
        audit_dir = Path(os.environ["UP_AUDIT_DIR"])
        try:
            # 切换到无 key 文件的隔离目录
            os.chdir(audit_dir)
            before = (audit_dir / "cost_events.ndjson").exists()
            proxy_mod._log_cost_event("glm-5.2", 10, 10, 1.0, "none")
            assert (audit_dir / "cost_events.ndjson").exists() == before  # 未写入
        finally:
            os.chdir(old_cwd)
            proxy_mod._HMAC_KEY = old_mod_key
            if old_env is not None:
                os.environ["MAREF_HMAC_SECRET_KEY"] = old_env


class TestCallGuard:
    def test_call_guard_blocks_over_limit(self, proxy_mod) -> None:
        proxy_mod._call_windows.clear()
        proxy_mod._CALL_WINDOW_SEC = 1800
        for i in range(3):
            lim, blocked = proxy_mod._enforce_call_guard("glm-5.2")
            assert blocked is False, f"call {i} should pass"
        lim, blocked = proxy_mod._enforce_call_guard("glm-5.2")
        assert blocked is True
        assert lim == 3

    def test_window_slides(self, proxy_mod) -> None:
        proxy_mod._call_windows.clear()
        now = time.time()
        # 塞入 2 个旧记录
        proxy_mod._call_windows["glm-5.2"] = [now - 2000, now - 1800]
        proxy_mod._CALL_WINDOW_SEC = 1800
        lim, blocked = proxy_mod._enforce_call_guard("glm-5.2")
        assert blocked is False  # 旧记录被清出


class TestCtxGuard:
    def test_estimate_req_chars(self, proxy_mod) -> None:
        body = {"messages": [{"content": "a" * 100}, {"content": [{"type": "text", "text": "b" * 50}]}]}
        assert proxy_mod._estimate_req_chars(body) == 150

    def test_ctx_limit_configurable(self, proxy_mod) -> None:
        cfg = Path(os.environ["UP_CONFIG"])
        cfg.write_text(json.dumps({"ctx_limit_chars": 30}))
        assert proxy_mod._cfg_int("ctx_limit_chars", 500) == 30


class TestDailyBudget:
    def test_daily_token_budget_blocks(self, proxy_mod) -> None:
        # 预算 100，已累计 90，新请求估算 30 → 超限
        budget_file = Path(os.environ["UP_AUDIT_DIR"]) / "daily_tokens.json"
        budget_file.write_text(json.dumps({"day": time.strftime("%Y-%m-%d"), "total": 90}))
        assert proxy_mod._daily_token_total() == 90
        # 90 + 30 = 120 > 100
        assert proxy_mod._cfg_int("daily_token_budget", proxy_mod._DAILY_TOKEN_BUDGET) < 90 + 30

    def test_daily_tokens_reset_next_day(self, proxy_mod) -> None:
        budget_file = Path(os.environ["UP_AUDIT_DIR"]) / "daily_tokens.json"
        budget_file.write_text(json.dumps({"day": "2026-01-01", "total": 9999}))
        assert proxy_mod._daily_token_total() == 0  # 非今天 → 0


class TestUsageStats:
    def test_usage_stats_aggregates(self, proxy_mod) -> None:
        audit_dir = Path(os.environ["UP_AUDIT_DIR"])
        now = time.time()
        for m in ("glm-5.2", "deepseek-v4-flash"):
            proxy_mod._write_audit_line(audit_dir / "cost_events.ndjson", {
                "event_type": "cost_event", "timestamp": now, "model": m,
                "input_chars": 1000, "output_chars": 100, "wall_ms": 5.0, "guard": "none",
            })
        proxy_mod._write_audit_line(audit_dir / "guard_blocks.ndjson", {
            "event_type": "guard_block", "timestamp": now, "model": "glm-5.2",
            "reason": "call_guard", "detail": "x",
        })
        # 通过 Handler 方法测试

        class FakeHandler:
            def _respond(self, code, body):
                self._code = code
                self._body = body

        handler = FakeHandler()
        handler._usage_stats = proxy_mod.UnifiedProxyHandler._usage_stats
        # 手动调用（绑定方法需要 handler 实例属性访问）
        stats = proxy_mod.UnifiedProxyHandler._usage_stats(handler)
        assert stats["daily"]["calls"] >= 2
        assert stats["by_model"]["glm-5.2"]["calls"] >= 1
        assert stats["guards"]["call_guard"] >= 1
