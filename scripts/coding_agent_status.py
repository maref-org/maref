#!/usr/bin/env python3
"""Coding Agent 治理注册状态检查 (增强版)

读取 configs/coding_agents_registry.json, 校验各 coding agent 的接入健康:
- 接入文件 (MCP/hook/adapter) 是否存在
- sidecar 是否可达
- 状态判定: connected / degraded / missing / unknown
- 运行时 KPI: 工具调用量、拦截率、平均延迟、信任分、HITL 触发率

输出 reports/coding_agents_status.json, 供治理引擎消费 (P-05 权重/P-04 僵死)。
数据源: 注册表 + sidecar telemetry + 本地 ObsEvent + MCP 决策日志
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from maref_config import REPO_DIR, RUNTIME_DIR, report_path, sidecar_auth_headers

# 允许环境覆盖 hooks 审计链路径（CI/多机场景不要依赖 ~/.claude 布局）
HOOKS_CHAIN = Path(
    os.environ.get("MAREF_HOOKS_AUDIT_LOG", "")
    or str(Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl")
).expanduser()

# hooks 链缓存 TTL：避免一次运行内重复扫链，同时防止常驻进程读到陈旧数据
_HOOKS_CACHE_TTL_SECONDS = 60.0
_hooks_cache: tuple[float, dict[str, dict[str, int]]] | None = None

# verdict 词表归一：hooks 链用 ALLOW/EXECUTED，Obs 侧历史上写 ok/allow
_ALLOW_VERDICTS = {"allow", "allowed", "ok", "executed", "success", "approved"}
_DENY_VERDICTS = {"deny", "denied", "blocked"}
_HITL_VERDICTS = {"ask_user", "hitl", "human_review"}
# 参与 KPI 统计的事件类型（hitl_triggered 是独立事件，不在 tool_call_end 里）
_TOOL_EVENT_TYPES = {
    "tool_call_start",
    "tool_call_end",
    "tool_call_intercepted",
    "hitl_triggered",
}


def _resolve(path: str) -> Path:
    """解析 $HOME / ${MAREF_REPO_DIR} 占位符。"""
    if not path:
        return Path("")
    p = path.replace("${MAREF_REPO_DIR}", str(REPO_DIR)).replace("${MAREF_RUNTIME_DIR}", str(RUNTIME_DIR))
    p = os.path.expanduser(p).replace("$HOME", str(Path.home()))
    return Path(p)


def _probe_sidecar(url: str, timeout: float = 1.5) -> bool:
    if not url:
        return False
    try:
        req = urllib.request.Request(f"{url}/api/health", headers=sidecar_auth_headers())
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def _fetch_sidecar_telemetry(sidecar_url: str, agent_id: str, since_hours: int = 24) -> dict[str, Any] | None:
    """从 sidecar 查询指定 agent 的遥测数据（A-4：带 Bearer，否则 401 静默全 0）。"""
    if not sidecar_url:
        return None
    try:
        since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()
        url = f"{sidecar_url.rstrip('/')}/api/telemetry/query"
        params = f"?source=maref-obs-{agent_id[:8]}&since={since_ts}&limit=1000"
        req = urllib.request.Request(url + params, method="GET", headers=sidecar_auth_headers())
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _read_local_obs_events(agent_id: str, since_hours: int = 24) -> list[dict]:
    """读取本地 ObsEvent 缓冲区"""
    obs_dir = Path.home() / ".maref" / "obs"
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    for f in obs_dir.glob("behavior_*.ndjson"):
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        # 过滤该 agent 的事件 (session_id 前缀匹配)
                        if ev.get("session_id", "").startswith(agent_id[:8]):
                            if ev.get("timestamp", 0) >= since_ts:
                                events.append(ev)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
    return events


def _read_mcp_decision_log(agent_id: str, since_hours: int = 24) -> list[dict]:
    """读取 MCP 决策日志 (如果存在)"""
    # MCP 决策日志在内存中，这里尝试从审计日志推导
    # P1-4: 审计日志优先 RUNTIME（生产 openclaw），fallback REPO（测试/开发）
    audit_log = RUNTIME_DIR / ".governance" / "governance_audit.jsonl"
    if not audit_log.exists():
        audit_log = REPO_DIR / ".governance" / "governance_audit.jsonl"
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    if not audit_log.exists():
        return events

    try:
        with open(audit_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("actor") == agent_id and ev.get("timestamp", 0) >= since_ts:
                        events.append(ev)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return events


def _hooks_24h_counts() -> dict[str, dict[str, int]]:
    """按 agent 聚合 hooks 审计链最近 24h verdict。

    hooks 链是工具调用的事实遥测（ALLOW/EXECUTED/DENY/BLOCKED），
    当 sidecar/obs 事件缺失时作为运行时 KPI 的回退数据源。
    """
    global _hooks_cache
    now_mono = time.monotonic()
    if _hooks_cache is not None and now_mono - _hooks_cache[0] < _HOOKS_CACHE_TTL_SECONDS:
        return _hooks_cache[1]

    counts: dict[str, dict[str, int]] = {}
    if not HOOKS_CHAIN.exists():
        _hooks_cache = (now_mono, counts)
        return counts
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
    try:
        with open(HOOKS_CHAIN, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = ev.get("timestamp")
                if not isinstance(ts, (int, float)) or ts < cutoff:
                    continue
                agent = str(ev.get("agent_id") or "")
                verdict = str(ev.get("verdict") or "").upper()
                if not agent or not verdict:
                    continue
                bucket = counts.setdefault(agent, {})
                bucket[verdict] = bucket.get(verdict, 0) + 1
    except OSError:
        pass
    _hooks_cache = (now_mono, counts)
    return counts


def _rate(part: int, total: int) -> float:
    """百分比，分母兜底并封顶，避免 hitl_rate 因口径差异 >100%。"""
    if total <= 0:
        return 0.0
    return round(min(100.0, part / total * 100.0), 2)


def _trust_score(
    allowed: int, denied: int, blocked: int, hitl: int, failed: int, total: int
) -> float:
    """统一信任分公式（hooks 与 sidecar 两路共用，保证跨源可比）。

    扣分项：拦截/拒绝 1.0x，HITL 0.3x，失败 0.5x（均按占比）。
    """
    if total <= 0:
        return 50.0
    intercepted_rate = (denied + blocked) / total * 100.0
    denied_rate = denied / total * 100.0
    hitl_rate = hitl / total * 100.0
    failed_rate = failed / total * 100.0
    score = 100.0 - intercepted_rate * 0.5 - denied_rate * 1.0 - hitl_rate * 0.3 - failed_rate * 0.5
    return round(max(0.0, min(100.0, score)), 1)


def _hooks_runtime_kpi(agent_id: str, kpi: dict[str, Any]) -> dict[str, Any]:
    counts = _hooks_24h_counts().get(agent_id) or {}
    allowed = max(counts.get("ALLOW", 0), counts.get("EXECUTED", 0))
    denied = counts.get("DENY", 0)
    blocked = counts.get("BLOCKED", 0)
    failed = counts.get("FAILED", 0)
    hitl = counts.get("HITL", 0)
    # hooks 的 verdict 是互斥裁决，HITL 也算一次被观察到的调用
    total = allowed + denied + blocked + failed + hitl
    if total == 0:
        return kpi
    denom = total
    kpi.update({
        "tool_calls_total": total,
        "tool_calls_allowed": allowed,
        "tool_calls_intercepted": blocked,
        "tool_calls_denied": denied,
        "tool_calls_hitl": hitl,
        "interception_rate": _rate(blocked + denied, denom),
        "hitl_rate": _rate(hitl, denom),
        "trust_score": _trust_score(allowed, denied, blocked, hitl, failed, denom),
        "kpi_source": "hooks_agent_24h",
    })
    return kpi


def _compute_runtime_kpi(
    agent_id: str,
    sidecar_url: str,
    telemetry_data: dict | None,
    local_events: list[dict],
    mcp_events: list[dict],
) -> dict[str, Any]:
    """计算运行时 KPI"""
    kpi: dict[str, Any] = {
        "tool_calls_total": 0,
        "tool_calls_allowed": 0,
        "tool_calls_intercepted": 0,
        "tool_calls_denied": 0,
        "tool_calls_hitl": 0,
        "interception_rate": 0.0,
        "hitl_rate": 0.0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "trust_score": 50.0,
        "hitl_events": 0,
        "unique_correlations": 0,
        # 三态：no_telemetry（无数据）/ sidecar_obs / hooks_agent_24h
        "kpi_source": "no_telemetry",
    }

    # 合并所有事件源（统一携带 event_type，避免只看 metadata 时字段丢失）
    all_tool_events: list[dict] = []

    def _with_event_type(payload: dict, fallback_type: str | None = None) -> dict:
        ev = dict(payload or {})
        if not ev.get("event_type") and fallback_type:
            ev["event_type"] = fallback_type
        return ev

    # 1. 来自 sidecar telemetry 的 ObsEvent 批量
    if telemetry_data and telemetry_data.get("results"):
        for entry in telemetry_data["results"]:
            data = _with_event_type(entry.get("data", {}))
            if data.get("event_type") in _TOOL_EVENT_TYPES:
                all_tool_events.append(data)

    # 2. 来自本地 ObsEvent
    for ev in local_events:
        meta = _with_event_type(ev.get("metadata", {}), ev.get("event_type"))
        if meta.get("event_type") in _TOOL_EVENT_TYPES:
            all_tool_events.append(meta)

    # 3. 来自 MCP 审计日志
    for ev in mcp_events:
        if ev.get("event_type") == "governance_decision":
            all_tool_events.append(_with_event_type(ev.get("metadata", {}), "governance_decision"))

    if not all_tool_events:
        return _hooks_runtime_kpi(agent_id, kpi)

    # 统计
    latencies = []
    correlations = set()
    tokens_in = 0
    tokens_out = 0
    cost = 0.0

    for ev in all_tool_events:
        event_type = ev.get("event_type")
        if event_type == "tool_call_start":
            kpi["tool_calls_total"] += 1
            corr = ev.get("correlation_id")
            if corr:
                correlations.add(corr)
        elif event_type == "tool_call_end":
            verdict = str(ev.get("verdict") or "").lower()
            if verdict in _ALLOW_VERDICTS:
                kpi["tool_calls_allowed"] += 1
            elif verdict in _DENY_VERDICTS:
                kpi["tool_calls_denied"] += 1
            elif verdict in _HITL_VERDICTS:
                kpi["tool_calls_hitl"] += 1
            lat = ev.get("latency_ms")
            if isinstance(lat, (int, float)) and lat > 0:
                latencies.append(float(lat))
            tokens_in += int(ev.get("tokens_input") or 0)
            tokens_out += int(ev.get("tokens_output") or 0)
            cost += float(ev.get("cost_usd") or 0.0)
        elif event_type in ("tool_call_intercepted", "hitl_triggered"):
            if event_type == "hitl_triggered":
                kpi["tool_calls_hitl"] += 1
            else:
                kpi["tool_calls_intercepted"] += 1

    kpi["unique_correlations"] = len(correlations)

    # 部分数据源只有 tool_call_end（无 start）→ 用裁决事件数回填总调用，
    # 避免出现 "total=0 但 allowed=3000" 的自相矛盾 KPI。
    observed_calls = kpi["tool_calls_allowed"] + kpi["tool_calls_denied"]
    kpi["tool_calls_total"] = max(
        kpi["tool_calls_total"], observed_calls, kpi["tool_calls_intercepted"], kpi["tool_calls_hitl"]
    )

    # 分母同时覆盖 start 计数与 HITL 计数，避免 hitl_rate 因口径不同而 >100%
    denom = max(kpi["tool_calls_total"], kpi["tool_calls_hitl"], 1)
    kpi["interception_rate"] = _rate(kpi["tool_calls_intercepted"] + kpi["tool_calls_denied"], denom)
    kpi["hitl_rate"] = _rate(kpi["tool_calls_hitl"], denom)
    kpi["hitl_events"] = kpi["tool_calls_hitl"]

    if latencies:
        latencies.sort()
        kpi["avg_latency_ms"] = round(sum(latencies) / len(latencies), 2)
        idx = int(len(latencies) * 0.95)
        kpi["p95_latency_ms"] = latencies[min(idx, len(latencies) - 1)]

    kpi["total_tokens"] = tokens_in + tokens_out
    kpi["total_cost_usd"] = round(cost, 6)

    # 统一信任分公式（与 hooks 回退路径一致）
    kpi["trust_score"] = _trust_score(
        kpi["tool_calls_allowed"],
        kpi["tool_calls_denied"],
        kpi["tool_calls_intercepted"],
        kpi["tool_calls_hitl"],
        0,
        denom,
    )
    if kpi["tool_calls_total"] == 0 and kpi["tool_calls_allowed"] == 0 and kpi["tool_calls_hitl"] == 0:
        return _hooks_runtime_kpi(agent_id, kpi)
    kpi["kpi_source"] = "sidecar_obs"

    return kpi


def check_agent(agent: dict) -> dict:
    integ = agent.get("integration", {})
    kind = integ.get("kind", "unknown")
    agent_id = agent["agent_id"]

    checks = {}

    entry = integ.get("entry")
    if entry:
        checks["entry_exists"] = _resolve(entry).exists()

    config = integ.get("config_path")
    if config:
        checks["config_exists"] = _resolve(config).exists()

    sidecar = integ.get("sidecar_url") or os.environ.get("MAREF_SIDECAR_URL", "")
    if not sidecar:
        try:
            from maref_config import sidecar_url as _probe_default_sidecar

            sidecar = _probe_default_sidecar()
        except Exception:
            sidecar = "http://127.0.0.1:8931"
    checks["sidecar_reachable"] = _probe_sidecar(sidecar) if sidecar else False

    declared = agent.get("status", "unknown")
    if declared == "degraded":
        effective = "degraded"
    elif kind == "hook":
        healthy = checks.get("entry_exists", False)
        effective = "connected" if healthy else "missing"
    elif kind in ("mcp", "adapter"):
        healthy = checks.get("config_exists", False)
        effective = "connected" if healthy else "missing"
    else:
        effective = declared

    # 收集运行时 KPI
    telemetry_data = _fetch_sidecar_telemetry(sidecar, agent_id) if checks["sidecar_reachable"] else None
    local_events = _read_local_obs_events(agent_id)
    mcp_events = _read_mcp_decision_log(agent_id)
    kpi = _compute_runtime_kpi(agent_id, sidecar, telemetry_data, local_events, mcp_events)

    return {
        "agent_id": agent_id,
        "display_name": agent.get("display_name", agent_id),
        "kind": agent.get("kind"),
        "did": agent.get("did"),
        "domain_weight": agent.get("domain_weight", 1),
        "integration_kind": kind,
        "declared_status": declared,
        "effective_status": effective,
        "checks": checks,
        "degraded_reason": agent.get("degraded_reason", ""),
        "runtime_kpi": kpi,
    }


def main() -> None:
    reg_path = REPO_DIR / "configs" / "coding_agents_registry.json"
    if not reg_path.exists():
        print(f"注册表不存在: {reg_path}")
        return

    with open(reg_path) as f:
        reg = json.load(f)

    print("=" * 70)
    print("Coding Agent 治理注册状态 + 运行时 KPI")
    print("=" * 70)

    results = []
    for agent in reg.get("agents", []):
        r = check_agent(agent)
        results.append(r)
        icon = {"connected": "✅", "degraded": "⚠️", "missing": "❌", "unknown": "❔"}.get(r["effective_status"], "?")
        kpi = r.get("runtime_kpi", {})

        print(f"\n{icon} {r['display_name']} ({r['agent_id']})")
        print(f"   接入: {r['integration_kind']}, 权重: {r['domain_weight']}")
        print(f"   声明: {r['declared_status']} → 实测: {r['effective_status']}")
        for k, v in r["checks"].items():
            print(f"   {'✅' if v else '❌'} {k}")

        # 显示 KPI
        if kpi:
            print(f"   📊 最近24h KPI (源: {kpi['kpi_source']}):")
            print(f"      总调用: {kpi['tool_calls_total']} | 通过: {kpi['tool_calls_allowed']} | 拦截: {kpi['tool_calls_intercepted']} | 拒绝: {kpi['tool_calls_denied']} | HITL: {kpi['tool_calls_hitl']}")
            print(f"      拦截率: {kpi['interception_rate']}% | HITL率: {kpi['hitl_rate']}%")
            print(f"      平均延迟: {kpi['avg_latency_ms']}ms | P95: {kpi['p95_latency_ms']}ms")
            print(f"      Token: {kpi['total_tokens']} | 成本: ${kpi['total_cost_usd']:.6f} | 信任分: {kpi['trust_score']}")
            print(f"      唯一关联ID: {kpi['unique_correlations']}")

        if r["degraded_reason"]:
            print(f"   ⚠️ {r['degraded_reason']}")

    summary = {
        "total": len(results),
        "connected": sum(1 for r in results if r["effective_status"] == "connected"),
        "degraded": sum(1 for r in results if r["effective_status"] == "degraded"),
        "missing": sum(1 for r in results if r["effective_status"] == "missing"),
        "unknown": sum(1 for r in results if r["effective_status"] == "unknown"),
    }

    # 聚合 KPI 总览
    total_calls = sum(r.get("runtime_kpi", {}).get("tool_calls_total", 0) for r in results)
    total_allowed = sum(r.get("runtime_kpi", {}).get("tool_calls_allowed", 0) for r in results)
    total_intercepted = sum(r.get("runtime_kpi", {}).get("tool_calls_intercepted", 0) for r in results)
    total_denied = sum(r.get("runtime_kpi", {}).get("tool_calls_denied", 0) for r in results)
    total_hitl = sum(r.get("runtime_kpi", {}).get("tool_calls_hitl", 0) for r in results)
    no_telemetry = [
        r["agent_id"] for r in results
        if r.get("runtime_kpi", {}).get("kpi_source") == "no_telemetry"
    ]

    print(f"\n{'=' * 70}")
    print(f"汇总: {summary['total']} agent | "
          f"✅{summary['connected']} ⚠️{summary['degraded']} ❌{summary['missing']} ❔{summary['unknown']}")
    print(f"全局 KPI (24h): 调用 {total_calls} | 通过 {total_allowed} | "
          f"拦截 {total_intercepted} | 拒绝 {total_denied} | HITL {total_hitl}")
    if no_telemetry:
        print(f"⚠️ 无遥测数据 (KPI 不参与健康判定): {', '.join(no_telemetry)}")

    out = report_path("coding_agents_status.json")
    with open(out, "w") as f:
        json.dump({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "global_kpi": {
                "tool_calls_total": total_calls,
                "tool_calls_allowed": total_allowed,
                "tool_calls_intercepted": total_intercepted,
                "tool_calls_denied": total_denied,
                "tool_calls_hitl": total_hitl,
                "agents_without_telemetry": no_telemetry,
            },
            "agents": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"报告已保存: {out}")


if __name__ == "__main__":
    main()
