#!/usr/bin/env python3
"""阶段1: 从红队日志提取攻击模式"""
import json, os, hashlib
from collections import Counter

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

def extract_patterns():
    entries = load_entries(RECURSIVE_LOG)
    trips = [e for e in entries if e.get('event_type') == 'circuit_breaker_trip']
    actions = Counter(e.get('action', 'unknown') for e in trips)
    
    patterns = []
    for action, count in actions.items():
        pattern = {
            "pattern_id": hashlib.sha256(action.encode()).hexdigest()[:12],
            "attack_class": action,
            "trigger": f"circuit_breaker_trip_{action}",
            "count": count,
            "source_rounds": [i for i, e in enumerate(trips) if e.get('action') == action][:10]
        }
        patterns.append(pattern)
    
    print("=" * 60)
    print("攻击模式抽取报告")
    print("=" * 60)
    print(f"\n总 trip 条目: {len(trips)}")
    print(f"提取模式数: {len(patterns)}")
    
    for p in patterns:
        print(f"\n  模式: {p['attack_class']}")
        print(f"  ID: {p['pattern_id']}")
        print(f"  触发次数: {p['count']}")
    
    output_path = "/Volumes/1TB-M2/public/maref/scripts/vaccine_pipeline/patterns.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(patterns, f, indent=2)
    
    print(f"\n模式已保存: {output_path}")
    return patterns

if __name__ == "__main__":
    extract_patterns()
