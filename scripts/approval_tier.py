#!/usr/bin/env python3
"""审批分层：低风险自动批准 + 抽样审计 (P-03) + T2-1 裁决质量判定规则

T2-1 改法2：对 unknown 分支补判定规则（风险分阈值 + 历史拒绝率），
验收指标：unknown 占比 ≤30% 且 deny+flag ≥1。
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone

from maref_config import AUDIT_LOG_V2 as AUDIT_LOG
from maref_config import RECURSIVE_AUDIT_LOG_V2 as RECURSIVE_LOG
from maref_config import report_path

VALID_VERDICTS = ("allow", "deny", "flag", "unknown")

# 治理绕过动作：无论历史 verdict 值一律升级为 flag（必须人工复核）
BYPASS_PREFIX = "governance_bypassed"
# 可逆稳定化动作白名单（低风险，历史拒绝率达标时判 allow）
STABILIZING_ACTIONS = {
    "oscillation_intervention",
    "force_stabilize",
    "auto_transition",
    "state_transition",
}
# 高敏感动作白名单（阈值判 flag）
SENSITIVE_ACTIONS = {
    "force_reset", "purge", "delete", "rm_rf", "hard_reset",
    "policy_overwrite", "trust_override",
}
# 风险阈值：达到该等级直接判 deny / flag
DENY_RISK = {"irreversible"}
FLAG_RISK = {"high"}
# 历史拒绝率阈值
D_RATE_DENY = 0.20  # 同 action 历史拒绝率 ≥20% → deny
D_RATE_FLAG = 0.05  # ≥5% → flag

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

def _verdict_of(e):
    """verdict 读取链：顶层 → metadata → 空。"""
    v = e.get("verdict")
    if v in VALID_VERDICTS:
        return v
    meta = e.get("metadata") or {}
    v = meta.get("verdict")
    if v in VALID_VERDICTS:
        return v
    return None

def _reason_of(e):
    return e.get("reason") or e.get("details") or ""

def _reclassify_unknown(e, deny_rates):
    """T2-1 改法2：unknown 判定规则（风险阈值 + 历史拒绝率 + 动作白名单）。

    返回 (新verdict, 判定轨迹字符串)。无法判定时保留 unknown。
    """
    action = e.get("action", "")
    risk = e.get("risk_level") or (e.get("metadata") or {}).get("risk_level") or "unknown"
    rate = deny_rates.get(action, 0.0)
    if risk in DENY_RISK:
        return "deny", f"risk_threshold:{risk}"
    if risk in FLAG_RISK:
        return "flag", f"risk_threshold:{risk}"
    if rate >= D_RATE_DENY:
        return "deny", f"hist_deny_rate:{rate:.0%}>={D_RATE_DENY:.0%}"
    if rate >= D_RATE_FLAG:
        return "flag", f"hist_deny_rate:{rate:.0%}>={D_RATE_FLAG:.0%}"
    if action.split(":")[0] in SENSITIVE_ACTIONS or action in SENSITIVE_ACTIONS:
        return "flag", "sensitive_action_whitelist"
    if action.split(":")[0] == BYPASS_PREFIX:
        return "flag", "governance_bypass_requires_review"
    if action in STABILIZING_ACTIONS and risk not in DENY_RISK | FLAG_RISK:
        return "allow", "stabilizing_reversible+hist_deny_rate<5%"
    return "unknown", "no_rule_matched"

def analyze_tiers():
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)

    decisions = [
        e for e in audit + recursive
        if e.get('event_type') == 'governance_decision'
    ]

    # 第一遍：原始 verdict + 同 action 历史拒绝率
    raw_counts = Counter()
    risk_counts = Counter()
    action_counts = Counter()
    deny_total = Counter()
    action_total = Counter()
    for e in decisions:
        v = _verdict_of(e) or "unknown"
        raw_counts[v] += 1
        r = e.get('risk_level') or (e.get('metadata') or {}).get('risk_level') or 'unknown'
        risk_counts[r] += 1
        action_counts[e.get('action', 'unknown')] += 1
        action_total[e.get('action', 'unknown')] += 1
        if v == 'deny':
            deny_total[e.get('action', 'unknown')] += 1
    deny_rates = {
        a: deny_total[a] / action_total[a]
        for a in action_total if action_total[a] > 0
    }

    # 第二遍：升级规则（bypass→flag）+ unknown 判定规则
    verdict_counts = Counter()
    reclassified = []
    for e in decisions:
        action = e.get("action", "")
        v = _verdict_of(e) or "unknown"
        if action.split(":")[0] == BYPASS_PREFIX and v != "flag":
            # 治理绕过：历史条目无论 allow/unknown 一律升级 flag
            v, rule = "flag", "governance_bypass_requires_review"
            reclassified.append({"action": action, "raw": _verdict_of(e) or "unknown", "verdict": v, "rule": rule})
        elif v == "unknown":
            nv, rule = _reclassify_unknown(e, deny_rates)
            if nv != "unknown":
                reclassified.append({"action": action, "raw": "unknown", "verdict": nv, "rule": rule})
            v = nv
        verdict_counts[v] += 1

    total = sum(verdict_counts.values()) or 1
    unknown_rate = verdict_counts.get('unknown', 0) / total
    deny_flag = verdict_counts.get('deny', 0) + verdict_counts.get('flag', 0)
    accept = bool(unknown_rate <= 0.30 and deny_flag >= 1)

    print("=" * 60)
    print("审批分层分析报告 (P-03) + T2-1 裁决质量")
    print("=" * 60)
    print(f"\n总治理决策: {len(decisions)}")
    print(f"  审计日志: {len(audit)}")
    print(f"  递归审计: {len(recursive)}")

    print("\n--- 裁决分布（原始） ---")
    for k, v in sorted(raw_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\n--- 裁决分布（判定后） ---")
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
    print(f"  判定重分类 : {len(reclassified)} 条")
    print(f"  结论: {'PASS' if accept else 'FAIL'}")

    low_count = risk_counts.get('low', 0)
    allow_count = verdict_counts.get('allow', 0)
    reject_rate = verdict_counts.get('deny', 0) / total * 100

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
    if risk_counts.get('irreversible', 0) > 0:
        print(f"⚠️ 存在 irreversible 条目: {risk_counts.get('irreversible')} 条，需宪法级别审查")

    output_path = str(report_path("approval_tier_report.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report = {
        "audit_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_decisions": len(decisions),
        "verdict_distribution": dict(verdict_counts),
        "verdict_distribution_raw": dict(raw_counts),
        "risk_distribution": dict(risk_counts),
        "action_distribution": dict(action_counts),
        "t2_1_acceptance": {
            "unknown_rate": round(unknown_rate, 4),
            "unknown_rate_max": 0.30,
            "deny_flag_count": deny_flag,
            "deny_flag_min": 1,
            "reclassified_count": len(reclassified),
            "reclassified": reclassified[:50],
            "verdict": "PASS" if accept else "FAIL",
        },
        "auto_approval_feasibility": "eligible" if low_count >= 20 and reject_rate < 5 else "insufficient_data",
        "constitutional_review": "required" if risk_counts.get('irreversible', 0) > 0 else "not required"
    }
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output_path}")

if __name__ == "__main__":
    analyze_tiers()
