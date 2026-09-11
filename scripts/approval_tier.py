#!/usr/bin/env python3
"""审批分层：低风险自动批准 + 抽样审计 (P-03)"""
import json, os
from collections import Counter

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit_v2.jsonl"
RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit_v2.jsonl"

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

def analyze_tiers():
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)

    decisions = [
        e for e in audit + recursive
        if e.get('event_type') == 'governance_decision'
    ]

    verdict_counts = Counter()
    risk_counts = Counter()
    action_counts = Counter()
    for e in decisions:
        v = e.get('verdict', 'unknown')
        verdict_counts[v] += 1
        r = e.get('risk_level', 'unknown')
        risk_counts[r] += 1
        action_counts[e.get('action', 'unknown')] += 1

    print("=" * 60)
    print("审批分层分析报告 (P-03)")
    print("=" * 60)
    print(f"\n总治理决策: {len(decisions)}")
    print(f"  审计日志: {len(audit)}")
    print(f"  递归审计: {len(recursive)}")

    print(f"\n--- 裁决分布 ---")
    for k, v in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print(f"\n--- 风险等级分布 ---")
    for k, v in sorted(risk_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print(f"\n--- 决策 action 分布 ---")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    low_count = risk_counts.get('low', 0)
    allow_count = verdict_counts.get('allow', 0)
    deny_count = verdict_counts.get('deny', 0)
    total = sum(verdict_counts.values())
    reject_rate = deny_count / total * 100 if total > 0 else 0

    print(f"\n--- 自动批准白名单建议 ---")
    print(f"条件: 历史拒绝率 <5% + 样本 >=20")
    print(f"低风险条目数: {low_count}")
    print(f"拒绝率: {reject_rate:.1f}%")
    print(f"allow 条目数: {allow_count}")
    if low_count >= 20 and reject_rate < 5:
        print(f"✅ 低风险类别满足自动批准条件")
    else:
        print(f"⚠️ 条件未满足 (样本: {low_count}/20, 拒绝率: {reject_rate:.1f}%/5%)")

    print(f"\n--- 宪法审查 ---")
    print("P-03 涉及治理裁决权边界")
    print("需确认: 自动批准属于条例层而非宪法层")
    if risk_counts.get('irreversible', 0) > 0:
        print(f"⚠️ 存在 irreversible 条目: {risk_counts.get('irreversible')} 条，需宪法级别审查")

    output_path = "/Volumes/1TB-M2/public/maref/reports/approval_tier_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report = {
        "audit_date": "2026-09-09",
        "total_decisions": len(decisions),
        "verdict_distribution": dict(verdict_counts),
        "risk_distribution": dict(risk_counts),
        "action_distribution": dict(action_counts),
        "auto_approval_feasibility": "eligible" if low_count >= 20 and reject_rate < 5 else "insufficient_data",
        "constitutional_review": "required" if risk_counts.get('irreversible', 0) > 0 else "not required"
    }
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output_path}")

if __name__ == "__main__":
    analyze_tiers()