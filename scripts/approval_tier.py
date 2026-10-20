#!/usr/bin/env python3
"""审批分层：低风险自动批准 + 抽样审计 (P-03) + T2-1 裁决质量指标"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone

from maref_config import AUDIT_LOG_V2 as AUDIT_LOG
from maref_config import RECURSIVE_AUDIT_LOG_V2 as RECURSIVE_LOG
from maref_config import report_path

VALID_VERDICTS = ("allow", "deny", "flag", "unknown")


def load_entries(path: str) -> list[dict]:
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
    return entries


def _verdict_of(entry: dict) -> str:
    """verdict 读取链：顶层 → metadata → unknown。"""
    verdict = entry.get("verdict")
    if verdict in VALID_VERDICTS:
        return verdict
    metadata = entry.get("metadata") or {}
    verdict = metadata.get("verdict")
    if verdict in VALID_VERDICTS:
        return verdict
    return "unknown"


def _risk_of(entry: dict) -> str:
    return entry.get("risk_level") or (entry.get("metadata") or {}).get("risk_level") or "unknown"


def analyze_tiers() -> None:
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)

    decisions = [
        e for e in audit + recursive
        if e.get("event_type") == "governance_decision"
    ]

    verdict_counts = Counter()
    risk_counts = Counter()
    action_counts = Counter()
    for entry in decisions:
        verdict_counts[_verdict_of(entry)] += 1
        risk_counts[_risk_of(entry)] += 1
        action_counts[entry.get("action", "unknown")] += 1

    total = sum(verdict_counts.values())
    unknown = verdict_counts.get("unknown", 0)
    unknown_rate = unknown / total if total else 0.0
    deny_flag = verdict_counts.get("deny", 0) + verdict_counts.get("flag", 0)
    acceptance = bool(unknown_rate <= 0.30 and deny_flag >= 1)

    print("=" * 60)
    print("审批分层分析报告 (P-03) + T2-1 裁决质量")
    print("=" * 60)
    print(f"\n总治理决策: {len(decisions)}")
    print(f"  审计日志: {len(audit)}")
    print(f"  递归审计: {len(recursive)}")

    print("\n--- 裁决分布 ---")
    for k, v in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\n--- 风险等级分布 ---")
    for k, v in sorted(risk_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\n--- 决策 action 分布 ---")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\n--- T2-1 验收 ---")
    print(f"  unknown 占比: {unknown_rate:.1%} (阈值 ≤30%) {'OK' if unknown_rate <= 0.30 else 'FAIL'}")
    print(f"  deny+flag  : {deny_flag} (阈值 ≥1) {'OK' if deny_flag >= 1 else 'FAIL'}")
    print(f"  结论: {'PASS' if acceptance else 'FAIL'}")

    low_count = risk_counts.get("low", 0)
    allow_count = verdict_counts.get("allow", 0)
    deny_count = verdict_counts.get("deny", 0)
    reject_rate = deny_count / total * 100 if total else 0.0

    print("\n--- 自动批准白名单建议 ---")
    print("条件: 历史拒绝率 <5% + 样本 >=20")
    print(f"低风险条目数: {low_count}")
    print(f"拒绝率: {reject_rate:.1f}%")
    print(f"allow 条目数: {allow_count}")
    if low_count >= 20 and reject_rate < 5:
        print("✅ 低风险类别满足自动批准条件")
    else:
        print(f"⚠️ 条件未满足 (样本: {low_count}/20, 拒绝率: {reject_rate:.1f}%/5%)")

    print("\n--- 宪法审查 ---")
    print("P-03 涉及治理裁决权边界")
    print("需确认: 自动批准属于条例层而非宪法层")
    if risk_counts.get("irreversible", 0) > 0:
        print(f"⚠️ 存在 irreversible 条目: {risk_counts.get('irreversible')} 条，需宪法级别审查")

    output_path = str(report_path("approval_tier_report.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report = {
        "audit_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_decisions": total,
        "verdict_distribution": dict(verdict_counts),
        "risk_distribution": dict(risk_counts),
        "action_distribution": dict(action_counts),
        "t2_1_acceptance": {
            "unknown_rate": round(unknown_rate, 4),
            "unknown_rate_max": 0.30,
            "deny_flag_count": deny_flag,
            "deny_flag_min": 1,
            "verdict": "PASS" if acceptance else "FAIL",
        },
        "auto_approval_feasibility": "eligible" if low_count >= 20 and reject_rate < 5 else "insufficient_data",
        "constitutional_review": "required" if risk_counts.get("irreversible", 0) > 0 else "not required",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output_path}")


if __name__ == "__main__":
    analyze_tiers()
