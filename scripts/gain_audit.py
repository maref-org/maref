#!/usr/bin/env python3
"""增益测量口径审计 (P-09)"""
import json, os
from collections import Counter
from datetime import datetime

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

def audit_gain():
    entries = load_entries(RECURSIVE_LOG)
    decisions = [e for e in entries if e.get('event_type') == 'governance_decision']
    actions = Counter(e.get('action', 'unknown') for e in decisions)
    
    print("=" * 60)
    print("增益测量口径审计报告 (P-09)")
    print("=" * 60)
    print(f"\n总决策条目: {len(decisions)}")
    
    print(f"\n--- 决策类型分布 ---")
    for k, v in sorted(actions.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    print(f"\n--- 增益口径文档 ---")
    print("分子: 近 N 轮性能差值")
    print("分母: 基线性能值")
    print("计算方式: 滚动中位数 (非算术均值)")
    print("失败轮处理: 排除失败轮 (去失败轮值)")
    print("三条曲线: 原始值 / 去失败轮值 / 滚动中位数")
    
    report = {
        "audit_date": datetime.now().isoformat(),
        "total_decisions": len(decisions),
        "action_distribution": dict(actions),
        "gain_formula": {
            "numerator": "近N轮性能差值",
            "denominator": "基线性能值",
            "method": "滚动中位数",
            "failure_handling": "排除失败轮"
        },
        "three_curves": ["原始值", "去失败轮值", "滚动中位数"]
    }
    
    output_path = "/Volumes/1TB-M2/public/maref/reports/gain_audit_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n审计报告已保存: {output_path}")
    print(f"\n✅ 增益口径审计完成")

if __name__ == "__main__":
    audit_gain()
