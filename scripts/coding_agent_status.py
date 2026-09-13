#!/usr/bin/env python3
"""Coding Agent 治理注册状态检查

读取 configs/coding_agents_registry.json, 校验各 coding agent 的接入健康:
- 接入文件 (MCP/hook/adapter) 是否存在
- sidecar 是否可达
- 状态判定: connected / degraded / missing / unknown

输出 reports/coding_agents_status.json, 供治理引擎消费 (P-05 权重/P-04 僵死)。
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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


def check_agent(agent: dict) -> dict:
    integ = agent.get("integration", {})
    kind = integ.get("kind", "unknown")

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

    declared = agent.get("status", "unknown")
    # degraded 声明优先: 即使文件仍在, 治理链路已知失效时不得报 connected
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

    return {
        "agent_id": agent["agent_id"],
        "display_name": agent.get("display_name", agent["agent_id"]),
        "kind": agent.get("kind"),
        "did": agent.get("did"),
        "domain_weight": agent.get("domain_weight", 1),
        "integration_kind": kind,
        "declared_status": declared,
        "effective_status": effective,
        "checks": checks,
        "degraded_reason": agent.get("degraded_reason", ""),
    }


def main() -> None:
    reg_path = REPO_DIR / "configs" / "coding_agents_registry.json"
    if not reg_path.exists():
        print(f"注册表不存在: {reg_path}")
        return

    with open(reg_path) as f:
        reg = json.load(f)

    print("=" * 62)
    print("Coding Agent 治理注册状态")
    print("=" * 62)

    results = []
    for agent in reg.get("agents", []):
        r = check_agent(agent)
        results.append(r)
        icon = {"connected": "✅", "degraded": "⚠️", "missing": "❌", "unknown": "❔"}.get(r["effective_status"], "?")
        print(f"\n{icon} {r['display_name']} ({r['agent_id']})")
        print(f"   接入: {r['integration_kind']}, 权重: {r['domain_weight']}")
        print(f"   声明: {r['declared_status']} → 实测: {r['effective_status']}")
        for k, v in r["checks"].items():
            print(f"   {'✅' if v else '❌'} {k}")
        if r["degraded_reason"]:
            print(f"   ⚠️ {r['degraded_reason']}")

    summary = {
        "total": len(results),
        "connected": sum(1 for r in results if r["effective_status"] == "connected"),
        "degraded": sum(1 for r in results if r["effective_status"] == "degraded"),
        "missing": sum(1 for r in results if r["effective_status"] == "missing"),
        "unknown": sum(1 for r in results if r["effective_status"] == "unknown"),
    }

    print(f"\n{'=' * 62}")
    print(f"汇总: {summary['total']} agent | "
          f"✅{summary['connected']} ⚠️{summary['degraded']} ❌{summary['missing']} ❔{summary['unknown']}")

    out = report_path("coding_agents_status.json")
    with open(out, "w") as f:
        json.dump({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "agents": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"报告已保存: {out}")


if __name__ == "__main__":
    main()
