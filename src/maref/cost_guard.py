"""MAREF Cost Guard — 开源自包含的 API 成本护栏（INC-2026-08-13-001 补强）。

v0.54+ 补强说明（根因 #1/#5 根治）：
    事故时成本护栏执行逻辑（CALL-GUARD/CTX-GUARD/BUDGET-GUARD）全部长在
    闭源 ``unified_proxy.py`` 内，开源仓库只有读取端（meta_monitor M4）与
    "指向闭源路径"的测试 —— 用户部署开源仓库后无任何可执行护栏，烧钱事故
    会重演。

    本模块把护栏执行逻辑提炼为开源可部署组件，任何代理/网关/中间件均可：
        from maref.cost_guard import CostGuard
        guard = CostGuard()
        limit, blocked = guard.enforce_call(model)
        blocked2 = guard.enforce_ctx(ctx_chars)
        blocked3 = guard.enforce_budget(est_tokens)
        guard.log_cost_event(model, in_chars, out_chars, wall_ms, "none")

    阈值从 ``~/.maref/proxy_config.json``（由 ``maref cost-policy`` 生成）读取，
    env 覆盖；每次调用/拦截写入 HMAC 签名审计（cost_events/guard_blocks.ndjson），
    与 meta_monitor ``check_cost`` / ``_cost_events_path`` 对齐。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path

# 高价模型清单（默认收紧阈值，与闭源 proxy 对齐）
_COSTY_MODELS = ("glm-5.2", "glm-4.7")

_CALL_WINDOW_SEC = 1800  # 30 分钟滑动窗口


def _audit_base() -> Path:
    """审计目录：与闭源 proxy 的 UP_AUDIT_DIR 对齐，保证 M4 可读。"""
    return Path(os.environ.get("UP_AUDIT_DIR", str(Path.home() / ".maref" / "audit")))


def _config_path() -> Path:
    return Path(os.environ.get("UP_CONFIG", str(Path.home() / ".maref" / "proxy_config.json")))


def _load_config() -> dict[str, object]:
    try:
        return json.loads(_config_path().read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _cfg_int(cfg: dict[str, object], key: str, default: int) -> int:
    v = cfg.get(key)
    if isinstance(v, (int, float)):
        return int(v)
    return default


def _audit_key() -> bytes:
    """HMAC 密钥：优先 env，其次 .maraf_hmac_key 文件（单一密钥源 G7）。"""
    env_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "") or ""
    if env_key:
        return env_key.encode()
    for cand in (Path.home() / ".maraf_hmac_key", Path.cwd() / ".maraf_hmac_key"):
        try:
            key = cand.read_text().strip()
            if key:
                return key.encode()
        except OSError:
            continue
    return b""


class CostGuard:
    """开源自包含成本护栏：调用次数 / 上下文长度 / 日 token 预算三层拦截。

    线程安全；每次拦截写 guard_block 审计，每次放行由调用方在成功后
    调用 :meth:`log_cost_event` 写 cost_event。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._call_windows: dict[str, list[float]] = {}
        self._cfg_cache: dict[str, object] = {}
        self._cfg_mtime = 0.0
        self._budget_day = ""
        self._budget_total = 0

    # ── 配置（热加载） ──────────────────────────────────────────────

    def _cfg(self) -> dict[str, object]:
        try:
            mtime = _config_path().stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime != self._cfg_mtime:
            self._cfg_cache = _load_config()
            self._cfg_mtime = mtime
        return self._cfg_cache

    def cfg_int(self, key: str, default: int) -> int:
        with self._lock:
            return _cfg_int(self._cfg(), key, default)

    # ── CALL-GUARD：30 分钟滑动窗口次数上限 ─────────────────────────

    def enforce_call(self, model: str, now: float | None = None) -> tuple[int, bool]:
        """检查并记账一次调用。返回 (limit, blocked)。

        blocked=True 表示模型近 30 分钟调用已达上限。
        """
        now = now if now is not None else time.time()
        with self._lock:
            limit = (
                self.cfg_int("call_hard_limit", 60)
                if model in _COSTY_MODELS
                else self.cfg_int("call_soft_limit", 300)
            )
            q = self._call_windows.setdefault(model, [])
            while q and now - q[0] > _CALL_WINDOW_SEC:
                q.pop(0)
            if len(q) >= limit:
                return limit, True
            q.append(now)
            return limit, False

    # ── CTX-GUARD：请求上下文长度上限 ───────────────────────────────

    @staticmethod
    def estimate_req_chars(body: dict[str, object]) -> int:
        """粗略估算请求消息总字符数（防上下文膨胀烧钱）。"""
        total = 0
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            return 0
        for m in messages:
            if not isinstance(m, dict):
                continue
            c = m.get("content", "")
            if isinstance(c, str):
                total += len(c)
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    t = b.get("text", "")
                    if not isinstance(t, str):
                        t = b.get("content", "")
                    if isinstance(t, str):
                        total += len(t)
        return total

    def enforce_ctx(self, ctx_chars: int) -> bool:
        """检查上下文长度是否超限。返回 blocked=True 表示应拦截。"""
        limit = self.cfg_int("ctx_limit_chars", 200_000)
        return ctx_chars > limit

    # ── BUDGET-GUARD：日 token 预算 ─────────────────────────────────

    def _daily_total(self) -> int:
        day = time.strftime("%Y-%m-%d")
        if day != self._budget_day:
            try:
                data = json.loads((_audit_base() / "daily_tokens.json").read_text())
                self._budget_total = int(data.get("total", 0)) if data.get("day") == day else 0
            except (OSError, ValueError, json.JSONDecodeError):
                self._budget_total = 0
            self._budget_day = day
        return self._budget_total

    def _record_daily_tokens(self, est: int) -> int:
        with self._lock:
            total = self._daily_total() + est
            try:
                path = _audit_base() / "daily_tokens.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"day": time.strftime("%Y-%m-%d"), "total": total}))
            except OSError:
                pass
            self._budget_total = total
            return total

    def enforce_budget(self, est_input_tokens: int) -> bool:
        """检查当日 token 预算是否超限（含本次估算）。返回 blocked=True。"""
        budget = self.cfg_int("daily_token_budget", 5_000_000)
        return self._daily_total() + est_input_tokens > budget

    def record_tokens(self, est_input_tokens: int) -> None:
        """调用成功后累计 token（与 enforce_budget 配套）。"""
        self._record_daily_tokens(est_input_tokens)

    # ── 审计写入（HMAC fail-closed，G1/G7） ─────────────────────────

    def _write_audit_line(self, path: Path, record: dict[str, object]) -> None:
        key = _audit_key()
        if not key:
            print(
                "[CostGuard] cost audit skipped: no HMAC key (fail-closed)",
                file=sys.stderr,
            )
            return
        payload = json.dumps(record, ensure_ascii=False, default=str)
        sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        line = json.dumps({**record, "hmac_signature": sig}, ensure_ascii=False)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write(line + "\n")
                f.flush()
        except OSError as e:
            print(f"[CostGuard] audit write failed: {e}", file=sys.stderr)

    def log_cost_event(
        self,
        model: str,
        input_chars: int,
        output_chars: int,
        wall_ms: float,
        guard: str,
    ) -> None:
        """记录一次 API 调用成本事件（调用成功后）。"""
        self._write_audit_line(_audit_base() / "cost_events.ndjson", {
            "event_type": "cost_event",
            "timestamp": time.time(),
            "model": model,
            "input_chars": input_chars,
            "output_chars": output_chars,
            "wall_ms": round(wall_ms, 1),
            "guard": guard,
            "actor": "maref_cost_guard",
        })

    def log_guard_block(self, model: str, reason: str, detail: str) -> None:
        """记录一次护栏拦截。"""
        self._write_audit_line(_audit_base() / "guard_blocks.ndjson", {
            "event_type": "guard_block",
            "timestamp": time.time(),
            "model": model,
            "reason": reason,
            "detail": detail,
            "actor": "maref_cost_guard",
        })

    def usage_stats(self, window_hours: int = 24) -> dict[str, object]:
        """聚合近 N 小时成本事件（供 /usage / maref usage / selfcheck）。"""
        now = time.time()
        hourly_calls = 0
        daily_calls = 0
        in_chars = 0
        out_chars = 0
        guarded = 0
        by_model: dict[str, dict[str, int]] = {}
        guards: dict[str, int] = {}
        base = _audit_base()
        for name, etype in (("cost_events.ndjson", "cost_event"), ("guard_blocks.ndjson", "guard_block")):
            path = base / name
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = d.get("timestamp", 0.0)
                if not isinstance(ts, (int, float)):
                    continue
                age = now - ts
                if age > window_hours * 3600:
                    continue
                if etype == "cost_event":
                    m = d.get("model", "?")
                    cell = by_model.setdefault(m, {"calls": 0, "in": 0, "out": 0})
                    cell["calls"] += 1
                    cell["in"] += int(d.get("input_chars", 0))
                    cell["out"] += int(d.get("output_chars", 0))
                    daily_calls += 1
                    if age <= 3600:
                        hourly_calls += 1
                else:
                    reason = d.get("reason", "?")
                    guards[reason] = guards.get(reason, 0) + 1
                    guarded += 1
        return {
            "hourly_calls": hourly_calls,
            "daily_calls": daily_calls,
            "input_chars": in_chars,
            "output_chars": out_chars,
            "guarded_24h": guarded,
            "guards": guards,
            "by_model": by_model,
            "daily_token_total": self._daily_total(),
        }
