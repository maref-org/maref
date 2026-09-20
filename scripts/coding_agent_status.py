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
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from maref_config import REPO_DIR, RUNTIME_DIR, report_path


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
        urllib.request.urlopen(f"{url}/api/health", timeout=timeout)
        return True
    except Exception:
        return False


def _fetch_sidecar_telemetry(sidecar_url: str, agent_id: str, since_hours: int = 24) -> dict[str, Any] | None:
    """从 sidecar 查询指定 agent 的遥测数据"""
    if not sidecar_url:
        return None
    try:
        since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()
        url = f"{sidecar_url.rstrip('/')}/api/telemetry/query"
        params = f"?source=maref-obs-{agent_id[:8]}&since={since_ts}&limit=1000"
        req = urllib.request.Request(url + params, method="GET")
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


def _compute_runtime_kpi(
    agent_id: str,
    sidecar_url: str,
    telemetry_data: dict | None,
    local_events: list[dict],
    mcp_events: list[dict],
) -> dict[str, Any]:
    """计算运行时 KPI"""
    kpi = {
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
    }

    # 合并所有事件源
    all_tool_events = []

    # 1. 来自 sidecar telemetry 的 ObsEvent 批量
    if telemetry_data and telemetry_data.get("results"):
        for entry in telemetry_data["results"]:
            data = entry.get("data", {})
            if data.get("event_type") in ("tool_call_start", "tool_call_end", "tool_call_intercepted"):
                all_tool_events.append(data)

    # 2. 来自本地 ObsEvent
    for ev in local_events:
        meta = ev.get("metadata", {})
        if ev.get("event_type") in ("tool_call_start", "tool_call_end", "tool_call_intercepted"):
            all_tool_events.append(meta)

    # 3. 来自 MCP 审计日志
    for ev in mcp_events:
        if ev.get("event_type") == "governance_decision":
            all_tool_events.append(ev.get("metadata", {}))

    if not all_tool_events:
        return kpi

    # 统计
    latencies = []
    correlations = set()
    tokens_in = 0
    tokens_out = 0
    cost = 0.0

    for ev in all_tool_events:
        if ev.get("event_type") == "tool_call_start":
            kpi["tool_calls_total"] += 1
            corr = ev.get("correlation_id")
            if corr:
                correlations.add(corr)
        elif ev.get("event_type") == "tool_call_end":
            verdict = ev.get("verdict", "").lower()
            if verdict == "allow":
                kpi["tool_calls_allowed"] += 1
            elif verdict == "deny":
                kpi["tool_calls_denied"] += 1
            elif verdict == "ask_user":
                kpi["tool_calls_hitl"] += 1
            lat = ev.get("latency_ms")
            if lat:
                latencies.append(lat)
            tokens_in += ev.get("tokens_input", 0)
            tokens_out += ev.get("tokens_output", 0)
            cost += ev.get("cost_usd", 0.0)
        elif ev.get("event_type") == "tool_call_intercepted":
            kpi["tool_calls_intercepted"] += 1

    kpi["unique_correlations"] = len(correlations)

    total_calls = kpi["tool_calls_total"] or 1
    kpi["interception_rate"] = round((kpi["tool_calls_intercepted"] + kpi["tool_calls_denied"]) / total_calls * 100, 2)
    kpi["hitl_rate"] = round(kpi["tool_calls_hitl"] / total_calls * 100, 2)

    if latencies:
        latencies.sort()
        kpi["avg_latency_ms"] = round(sum(latencies) / len(latencies), 2)
        idx = int(len(latencies) * 0.95)
        kpi["p95_latency_ms"] = latencies[min(idx, len(latencies) - 1)]

    kpi["total_tokens"] = tokens_in + tokens_out
    kpi["total_cost_usd"] = round(cost, 6)

    # 信任分估算 (基于拦截率、HITL 率、错误率)
    trust = 100.0
    trust -= kpi["interception_rate"] * 0.5
    trust -= kpi["hitl_rate"] * 0.3
    trust -= (kpi["tool_calls_denied"] / total_calls * 100) * 1.0
    kpi["trust_score"] = round(max(0.0, min(100.0, trust)), 1)

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
    if sidecar:
        checks["sidecar_reachable"] = _probe_sidecar(sidecar)
    else:
        checks["sidecar_reachable"] = False

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
            print(f"   📊 最近24h KPI:")
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
    total_intercepted = sum(r.get("runtime_kpi", {}).get("tool_calls_intercepted", 0) for r in results)
    total_denied = sum(r.get("runtime_kpi", {}).get("tool_calls_denied", 0) for r in results)
    total_hitl = sum(r.get("runtime_kpi", {}).get("tool_calls_hitl", 0) for r in results)

    print(f"\n{'=' * 70}")
    print(f"汇总: {summary['total']} agent | "
          f"✅{summary['connected']} ⚠️{summary['degraded']} ❌{summary['missing']} ❔{summary['unknown']}")
    print(f"全局 KPI (24h): 调用 {total_calls} | 拦截 {total_intercepted} | 拒绝 {total_denied} | HITL {total_hitl}")

    out = report_path("coding_agents_status.json")
    with open(out, "w") as f:
        json.dump({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "global_kpi": {
                "tool_calls_total": total_calls,
                "tool_calls_intercepted": total_intercepted,
                "tool_calls_denied": total_denied,
                "tool_calls_hitl": total_hitl,
            },
            "agents": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"报告已保存: {out}")


if __name__ == "__main__":
    main()