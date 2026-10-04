#!/usr/bin/env python3
"""Agent 覆盖四方对账（T1-5 / G-08）。

**口径问题**（audit 2026-10-03 G-08）: registry 64（07-24 陈旧）/ active 28 /
internal/agents 44 文件 / coding registry 5，四处数字互不一致且无任何
源支撑文档里的「180+」声明 → 覆盖率无法证明。

**本脚本做法**:
1. **唯一口径源（SSOT）**= openclaw `agent_heartbeat.db`（心跳 daemon 每日刷新），
   实测 162 条 / 151 active_24h / 最新心跳 <1h。
2. `.governance/agent_registry.json` 由 SSOT **派生刷新**（改法2：不再 70 天陈旧）。
3. 「180+」查无源 → 降级为 unverified claim 记入 `declared_180.resolution`
   （方案 T1-5 选项3的反面处置：无清单可设源则不作口径）。
4. `gaps[]` 只收**可验证的口径差**：
   - coding registry 中 status=connected 的 agent 缺席心跳库
   - 派生 registry 的 generated_at 非今日
   - active_24h == 0（心跳源死）
5. `orphan[]` = 心跳库中 >7 天无心跳的僵尸注册项（清理线索）。

用法:
    python3 scripts/agent_coverage_reconcile.py            # 对账 + 刷新派生 registry
    python3 scripts/agent_coverage_reconcile.py --no-refresh
退出码: 0 = gaps 为空；1 = 存在未解释差异。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
CODING_REGISTRY = REPO_DIR / "configs" / "coding_agents_registry.json"
GOV_REGISTRY = REPO_DIR / ".governance" / "agent_registry.json"


def _openclaw_root() -> Path | None:
    """openclaw（Track A 运行时）仓根解析：env → ~/.maref/runtime_dir.json。

    Leak Detection CI 禁止 /Volumes 硬编码（leak-detection.yml），
    故与 T0-2 同模式走配置解析；解析不到时由 gaps 报 heartbeat_db_unavailable。
    """
    env = os.environ.get("MAREF_OPENCLAW_ROOT", "").strip()
    if env:
        return Path(env)
    try:
        cfg = json.loads((Path.home() / ".maref" / "runtime_dir.json").read_text())
        cand = cfg.get("runtime_dir")
        if cand and Path(cand).is_dir():
            return Path(cand)
    except (OSError, ValueError, TypeError):
        pass
    return None


_OPENCLAW = _openclaw_root()
HEARTBEAT_DB = _OPENCLAW / ".openclaw" / "agent_heartbeat.db" if _OPENCLAW else None
INTERNAL_AGENTS = _OPENCLAW / "internal" / "agents" if _OPENCLAW else None

STALE_ORPHAN_DAYS = 7
PLAN_CLAIMED_180 = 180
PLAN_CLAIMED_INTERNAL_DEFS = 44  # 方案 T1-5 原文数字（实测会对照输出）


def _load_coding_registry() -> list[dict]:
    if not CODING_REGISTRY.exists():
        return []
    data = json.loads(CODING_REGISTRY.read_text())
    return data.get("agents", [])


def _load_heartbeat_db() -> tuple[list[dict], str | None]:
    """返回 (rows, error)。rows 含 agent_id/name/trust_level/trust_score/
    last_heartbeat/registered_at/status。"""
    if HEARTBEAT_DB is None:
        return [], "openclaw root 未解析（配置 MAREF_OPENCLAW_ROOT 或 ~/.maref/runtime_dir.json）"
    if not HEARTBEAT_DB.exists():
        return [], f"heartbeat db 不存在: {HEARTBEAT_DB}"
    conn = sqlite3.connect(f"file:{HEARTBEAT_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT agent_id, name, trust_level, trust_score, last_heartbeat, "
                "registered_at, status FROM agent_heartbeats"
            )
        ]
    finally:
        conn.close()
    return rows, None


def _count_internal_defs() -> int:
    if INTERNAL_AGENTS is None or not INTERNAL_AGENTS.is_dir():
        return 0
    return sum(
        1
        for p in INTERNAL_AGENTS.rglob("*.py")
        if p.name != "__init__.py" and "__pycache__" not in p.parts
    )


def _refresh_registry(rows: list[dict], generated_at: str) -> dict:
    """由心跳库派生刷新 .governance/agent_registry.json（改法2）。"""
    agents = sorted(
        (
            {
                "agent_id": r["agent_id"],
                "name": r["name"],
                "status": r["status"] or "unknown",
                "trust_level": r["trust_level"],
                "trust_score": r["trust_score"],
                "last_heartbeat": r["last_heartbeat"],
                "registered_at": r["registered_at"],
            }
            for r in rows
        ),
        key=lambda a: a["agent_id"],
    )
    payload = {
        "version": 2,
        "generated_at": generated_at,
        "source": f"derived_from:{HEARTBEAT_DB or 'unresolved'}",
        "agents": agents,
    }
    GOV_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = GOV_REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(GOV_REGISTRY)
    return {"path": str(GOV_REGISTRY), "count": len(agents), "generated_at": generated_at}


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 覆盖四方对账")
    parser.add_argument("--no-refresh", action="store_true", help="不写派生 registry")
    parser.add_argument(
        "--output", default=str(REPO_DIR / "reports" / "agent_coverage_report.json")
    )
    args = parser.parse_args()

    now = datetime.now(UTC)
    today = now.date().isoformat()
    now_ts = now.timestamp()

    coding = _load_coding_registry()
    heartbeat_rows, db_error = _load_heartbeat_db()
    internal_defs = _count_internal_defs()

    hb_ids = {r["agent_id"] for r in heartbeat_rows}
    active_24h = sum(
        1 for r in heartbeat_rows if now_ts - float(r["last_heartbeat"] or 0) < 86400
    )
    newest_age_h = (
        round(
            (now_ts - max(float(r["last_heartbeat"] or 0) for r in heartbeat_rows)) / 3600,
            2,
        )
        if heartbeat_rows
        else None
    )

    # —— gaps：只收可验证的口径差 ——
    gaps: list[dict] = []
    if db_error:
        gaps.append({"kind": "heartbeat_db_unavailable", "detail": db_error})
    else:
        # ① connected 的 coding agent 必须有心跳（unknown/degraded 不强制）
        for a in coding:
            if a.get("status") == "connected" and a["agent_id"] not in hb_ids:
                gaps.append(
                    {
                        "kind": "connected_coding_agent_missing_from_heartbeat",
                        "agent_id": a["agent_id"],
                    }
                )
        # ② 心跳源必须活着
        if active_24h == 0:
            gaps.append({"kind": "no_active_heartbeat_24h"})

    # —— 派生刷新 registry（改法2）——
    generated_at = now.isoformat()
    if args.no_refresh and GOV_REGISTRY.exists():
        old = json.loads(GOV_REGISTRY.read_text())
        generated_at = str(old.get("generated_at", ""))
    if not args.no_refresh and heartbeat_rows:
        registry_info = _refresh_registry(heartbeat_rows, generated_at)
    else:
        registry_info = {
            "path": str(GOV_REGISTRY),
            "count": len(json.loads(GOV_REGISTRY.read_text()).get("agents", []))
            if GOV_REGISTRY.exists()
            else 0,
            "generated_at": generated_at,
            "refreshed": False,
        }
    # ③ 派生 registry 必须是今日（--no-refresh 时豁免，该模式仅用于测试）
    if not args.no_refresh and not generated_at.startswith(today):
        gaps.append(
            {"kind": "registry_generated_at_stale", "value": generated_at, "today": today}
        )

    # —— orphan：>7 天无心跳的僵尸注册 ——
    orphan = [
        {
            "agent_id": r["agent_id"],
            "age_days": round((now_ts - float(r["last_heartbeat"] or 0)) / 86400, 1),
        }
        for r in heartbeat_rows
        if now_ts - float(r["last_heartbeat"] or 0) > STALE_ORPHAN_DAYS * 86400
    ]

    connected = [a["agent_id"] for a in coding if a.get("status") == "connected"]
    report = {
        "generated_at": generated_at,
        "declared_180": {
            "claim": "180+",
            "count": PLAN_CLAIMED_180,
            "supported": False,
            "closest_source": {"heartbeat_db": len(heartbeat_rows)},
            "resolution": "demoted_to_unverified",
            "evidence": "openclaw 侧唯一可数清单为 agent_heartbeat.db（162 条），"
            "README/AGENTS/docs 均无 180 口径出处（G-08 审计 2026-10-03）",
        },
        "registry": {**registry_info, "derived_from": str(HEARTBEAT_DB)},
        "active_24h": active_24h,
        "internal_defs": {
            "path": str(INTERNAL_AGENTS) if INTERNAL_AGENTS else None,
            "count": internal_defs,
            "plan_claimed": PLAN_CLAIMED_INTERNAL_DEFS,
        },
        "coding_registry": {
            "path": str(CODING_REGISTRY),
            "count": len(coding),
            "connected": connected,
            "connected_in_heartbeat": [i for i in connected if i in hb_ids],
        },
        "heartbeat_db": {
            "path": str(HEARTBEAT_DB) if HEARTBEAT_DB else None,
            "count": len(heartbeat_rows),
            "active_24h": active_24h,
            "newest_heartbeat_age_h": newest_age_h,
            "role": "ssot",
            "error": db_error,
        },
        "gaps": gaps,
        "orphan": orphan,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print("=" * 70)
    print("Agent 覆盖四方对账（SSOT = openclaw agent_heartbeat.db）")
    print("=" * 70)
    print(f"  heartbeat_db : {report['heartbeat_db']['count']} 条"
          f"（active_24h={active_24h}, 最新心跳 {newest_age_h}h 前）")
    print(f"  registry     : {registry_info['count']} 条"
          f"（generated_at={registry_info['generated_at'][:19]}）")
    print(f"  coding       : {len(coding)} 条（connected={connected}）")
    print(f"  internal_defs: {internal_defs}（方案原文 {PLAN_CLAIMED_INTERNAL_DEFS}）")
    print(f"  180+ 声明    : 无源 → 已降级 unverified（closest={len(heartbeat_rows)}）")
    print(f"  gaps         : {len(gaps)}"
          + ("" if not gaps else " → " + json.dumps(gaps, ensure_ascii=False)))
    print(f"  orphan       : {len(orphan)}（>{STALE_ORPHAN_DAYS}d 无心跳）")
    print(f"  报告: {out}")
    return 0 if not gaps else 1


if __name__ == "__main__":
    sys.exit(main())
