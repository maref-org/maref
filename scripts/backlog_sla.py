#!/usr/bin/env python3
"""积压提案 SLA 治理 (P-08)"""
import json, os
from datetime import datetime, timedelta
from collections import Counter

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit.jsonl"
RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit.jsonl"

def load_entries(path):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                pass
    return entries

def analyze_backlog():
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)

    now = datetime.now()
    backlog = {"high": [], "medium": [], "low": [], "unknown": []}

    for entry in audit + recursive:
        ts = entry.get('timestamp')
        if not ts:
            continue

        try:
            t = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
            age_hours = (now - t.replace(tzinfo=None)).total_seconds() / 3600
        except:
            continue

        event_type = entry.get('event_type', 'unknown')
        if event_type == 'governance_decision':
            details = entry.get('details', {})
            risk = "unknown"
            if isinstance(details, dict):
                risk = details.get('risk_level', 'unknown')

            if age_hours > 168 and risk == "high":
                backlog["high"].append({
                    "id": entry.get('id', 'unknown'),
                    "age_hours": round(age_hours, 1),
                    "action": entry.get('action', 'unknown'),
                    "risk": risk
                })
            elif age_hours > 336:
                backlog["medium"].append({
                    "id": entry.get('id', 'unknown'),
                    "age_hours": round(age_hours, 1),
                    "action": entry.get('action', 'unknown'),
                    "risk": risk
                })
            elif age_hours > 168:
                backlog["low"].append({
                    "id": entry.get('id', 'unknown'),
                    "age_hours": round(age_hours, 1),
                    "action": entry.get('action', 'unknown'),
                    "risk": risk
                })

    print("=" * 60)
    print("积压提案 SLA 治理报告 (P-08)")
    print("=" * 60)

    print(f"\n--- 积压分布 ---")
    total_backlog = sum(len(v) for v in backlog.values())
    print(f"总积压: {total_backlog}")
    print(f"  高危 (>7d): {len(backlog['high'])}")
    print(f"  中危 (>14d): {len(backlog['medium'])}")
    print(f"  低危 (>7d): {len(backlog['low'])}")
    print(f"  未知风险: {len(backlog['unknown'])}")

    print(f"\n--- SLA 目标 ---")
    print("高危积压 7d 清零率目标: 100%")
    print(f"当前高危积压: {len(backlog['high'])}")
    clearance = "✅ 达标" if len(backlog['high']) == 0 else f"⚠️ {len(backlog['high'])} 条待清零"
    print(f"清零状态: {clearance}")

    if backlog['high']:
        print(f"\n--- 高危积压详情 (前5条) ---")
        for item in backlog['high'][:5]:
            print(f"  ID: {item['id']}, 积压: {item['age_hours']}h, 操作: {item['action']}")

    output_path = "/Volumes/1TB-M2/public/maref/reports/backlog_sla_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({
            "audit_date": datetime.now().isoformat(),
            "total_backlog": total_backlog,
            "high_risk_count": len(backlog['high']),
            "sla_target": "高危7d清零率100%",
            "sla_met": len(backlog['high']) == 0,
            "backlog": {k: v[:10] for k, v in backlog.items()}
        }, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output_path}")

if __name__ == "__main__":
    analyze_backlog()