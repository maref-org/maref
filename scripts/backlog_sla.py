#!/usr/bin/env python3
"""积压提案 SLA 治理 (P-08) + P2-8 A-x 审计 backlog 注入"""
import json
import os
from datetime import datetime, timezone

from maref_config import AUDIT_LOG, REPO_DIR, report_path
from maref_config import RECURSIVE_AUDIT_LOG as RECURSIVE_LOG


def load_entries(path):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except Exception:
                pass
    return entries

def _parse_timestamp(ts):
    """兼容 float unix 与 ISO 字符串（P2-8 修复: 旧版 fromisoformat 对 float 全部 skip）。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (OSError, OverflowError, ValueError, TypeError):
            return None

def _age_hours(t):
    now = datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (now - t).total_seconds() / 3600

def _known_audit_backlog():
    """P2-8: 根因报告 A-x 未进提案流时的兜底工单（有状态 JSON 则动态年龄）。"""
    items = []
    # A-2: 进化引擎停滞
    evo_path = REPO_DIR / "reports" / "evolution_daemon_status.json"
    try:
        evo = json.loads(evo_path.read_text()) if evo_path.exists() else {}
        status = evo.get("status", {})
        if not status.get("daemon_running", False) and status.get("hours_stale"):
            items.append({
                "id": "A-2",
                "action": "evolution_daemon_restart",
                "risk": "high",
                "age_hours": round(float(status["hours_stale"]), 1),
                "source": "audit_rootcause_backlog",
                "detail": f"进化守护进程停滞 {status.get('days_stale', '?')} 天",
            })
    except Exception:
        items.append({
            "id": "A-2",
            "action": "evolution_daemon_restart",
            "risk": "high",
            "age_hours": 1777.0,
            "source": "audit_rootcause_backlog",
            "detail": "进化守护进程停滞（状态 JSON 不可读）",
        })
    # A-4: coding agent 治理 KPI 全 0（输出文件为 coding_agents_status.json 复数）
    ca_path = REPO_DIR / "reports" / "coding_agents_status.json"
    if not ca_path.exists():
        ca_path = REPO_DIR / "reports" / "coding_agent_status.json"
    try:
        ca = json.loads(ca_path.read_text()) if ca_path.exists() else {}
        if isinstance(ca.get("status"), dict):
            ca = {**ca, **ca["status"]}
        gkpi = ca.get("global_kpi") or {}
        kpi_zero = (
            ca.get("kpi_24h_all_zero") is True
            or gkpi.get("tool_calls_total") == 0
            or ca.get("total_24h") == 0
            or ca.get("calls_24h") == 0
        )
        agents = ca.get("agents") or []
        reachable_fail = ca.get("sidecar_reachable") is False or any(
            isinstance(a, dict) and (a.get("checks") or {}).get("sidecar_reachable") is False
            for a in agents
            if isinstance(a, dict)
        )
        if kpi_zero or reachable_fail:
            age = ca.get("hours_stale") or ca.get("age_hours") or 168.0
            items.append({
                "id": "A-4",
                "action": "coding_agent_governance_kpi",
                "risk": "medium",
                "age_hours": round(float(age) or 168.0, 1),
                "source": "audit_rootcause_backlog",
                "detail": "24h coding agent 治理调用为 0 / sidecar_reachable 失败",
            })
    except Exception:
        # 报告缺失也注入（根因 A-4 实况）
        items.append({
            "id": "A-4",
            "action": "coding_agent_governance_kpi",
            "risk": "medium",
            "age_hours": 168.0,
            "source": "audit_rootcause_backlog",
            "detail": "coding agent 状态报告缺失 / 24h KPI 未知",
        })
    return items

def analyze_backlog():
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)

    backlog = {"high": [], "medium": [], "low": [], "unknown": []}

    for entry in audit + recursive:
        ts = entry.get('timestamp')
        t = _parse_timestamp(ts)
        if t is None:
            continue
        age_hours = _age_hours(t)

        event_type = entry.get('event_type', 'unknown')
        if event_type == 'governance_decision':
            details = entry.get('details', {})
            risk = "unknown"
            if isinstance(details, dict):
                risk = details.get('risk_level', 'unknown')
            elif isinstance(details, str) and 'high' in details.lower():
                risk = 'high'

            item = {
                "id": entry.get('id', 'unknown'),
                "age_hours": round(age_hours, 1),
                "action": entry.get('action', 'unknown'),
                "risk": risk,
            }
            if age_hours > 168 and risk == "high":
                backlog["high"].append(item)
            elif age_hours > 336:
                backlog["medium"].append(item)
            elif age_hours > 168:
                backlog["low"].append(item)

    # P2-8: 注入已知 A-x 审计工单（去重 by id）
    known_ids = {i["id"] for bucket in backlog.values() for i in bucket}
    for kn in _known_audit_backlog():
        if kn["id"] in known_ids:
            continue
        if kn["risk"] == "high":
            backlog["high"].append(kn)
        elif kn["risk"] == "medium":
            backlog["medium"].append(kn)
        else:
            backlog["unknown"].append(kn)

    print("=" * 60)
    print("积压提案 SLA 治理报告 (P-08 + P2-8 A-x 注入)")
    print("=" * 60)

    print("\n--- 积压分布 ---")
    total_backlog = sum(len(v) for v in backlog.values())
    print(f"总积压: {total_backlog}")
    print(f"  高危 (>7d 或 A-x high): {len(backlog['high'])}")
    print(f"  中危 (>14d 或 A-x medium): {len(backlog['medium'])}")
    print(f"  低危 (>7d): {len(backlog['low'])}")
    print(f"  未知风险: {len(backlog['unknown'])}")

    print("\n--- SLA 目标 ---")
    print("高危积压 7d 清零率目标: 100%")
    print(f"当前高危积压: {len(backlog['high'])}")
    clearance = "✅ 达标" if len(backlog['high']) == 0 else f"⚠️ {len(backlog['high'])} 条待清零"
    print(f"清零状态: {clearance}")

    # T2-2 改法3: medium 14d SLA 指标 (p95 年龄天数 + 清零率)
    medium_ages_d = sorted(i.get("age_hours", 0) / 24.0 for i in backlog["medium"])
    if medium_ages_d:
        n = len(medium_ages_d)
        k = 0.95 * (n - 1)
        f, c = int(k), k - int(k)
        p95 = (medium_ages_d[f] + c * (medium_ages_d[f + 1] - medium_ages_d[f])
               if f + 1 < n else medium_ages_d[f])
        over_14d = sum(1 for a in medium_ages_d if a > 14)
        cleared_rate = (n - over_14d) / n
    else:
        p95, over_14d, cleared_rate = 0.0, 0, 1.0
    medium_sla_met = p95 < 14.0

    print("\n--- 中危 14d SLA (T2-2) ---")
    print(f"medium_age_p95: {p95:.2f}d (目标 <14d) {'✅' if medium_sla_met else '⚠️'}")
    print(f">14d 条数: {over_14d}; 14d 内清零率: {cleared_rate:.0%}")

    if backlog['high']:
        print("\n--- 高危积压详情 (前5条) ---")
        for item in backlog['high'][:5]:
            print(f"  ID: {item['id']}, 积压: {item['age_hours']}h, 操作: {item['action']}")
            if item.get('source') == 'audit_rootcause_backlog':
                print(f"    (来源: 审计根因 backlog) {item.get('detail', '')}")

    output_path = str(report_path("backlog_sla_report.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # T2-2: 清零留痕 — 上一版 medium 中本次消失的条目转入 cleared_medium,
    # 防止「修复即失忆」导致闭环提案源丢失 (历史 cleared 合并保留)。
    prev_cleared = []
    prev_medium = []
    if os.path.exists(output_path):
        try:
            with open(output_path) as pf:
                prev = json.loads(pf.read())
            prev_cleared = prev.get("cleared_medium", []) or []
            prev_medium = (prev.get("backlog", {}) or {}).get("medium", []) or []
        except Exception:
            pass
    cur_ids = {i["id"] for i in backlog["medium"]}
    now_iso = datetime.now().isoformat()
    newly_cleared = [
        dict(i, cleared_at=now_iso, clear_reason="remediated_or_stale")
        for i in prev_medium if i.get("id") not in cur_ids
    ]
    known_cleared = {i.get("id") for i in prev_cleared}
    cleared_medium = prev_cleared + [
        i for i in newly_cleared if i.get("id") not in known_cleared
    ]

    with open(output_path, 'w') as f:
        json.dump({
            "audit_date": datetime.now().isoformat(),
            "total_backlog": total_backlog,
            "high_risk_count": len(backlog['high']),
            "sla_target": "高危7d清零率100%",
            "sla_met": len(backlog['high']) == 0,
            "medium_age_p95": round(p95, 2),
            "medium_age_p95_days": round(p95, 2),
            "medium_over_14d_count": over_14d,
            "medium_14d_cleared_rate": round(cleared_rate, 4),
            "medium_sla_met": medium_sla_met,
            "cleared_medium": cleared_medium,
            "backlog": {k: v[:10] for k, v in backlog.items()},
            "p2_injected": [i["id"] for b in backlog.values() for i in b if i.get("source") == "audit_rootcause_backlog"],
        }, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output_path}")

if __name__ == "__main__":
    analyze_backlog()
