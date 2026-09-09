#!/usr/bin/env python3
"""已批准提案 5% 月度翻案抽查 (P-01)"""
import json, os, random
from datetime import datetime

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit_v2.jsonl"

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

def resample():
    entries = load_entries(AUDIT_LOG)
    
    approved = [
        e for e in entries 
        if e.get('verdict') == 'allow'
    ]
    
    sample_size = max(5, int(len(approved) * 0.05))
    sample = random.sample(approved, min(sample_size, len(approved)))
    
    print("=" * 60)
    print("翻案抽查报告 (P-01)")
    print("=" * 60)
    print(f"总 approved 条目: {len(approved)}")
    print(f"抽样数量: {len(sample)}")
    print(f"抽样比例: {len(sample)/len(approved)*100:.1f}%" if approved else "N/A")
    
    resample_log = []
    for entry in sample:
        resample_log.append({
            "id": entry.get('id'),
            "timestamp": entry.get('timestamp'),
            "action": entry.get('action'),
            "resampled_at": datetime.now().isoformat(),
            "original_verdict_hidden": True
        })
    
    output_path = "/Volumes/1TB-M2/public/maref/reports/resample_log.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(resample_log, f, indent=2)
    
    print(f"\n抽样日志已保存: {output_path}")
    print("注意: 原批准标记已隐藏，等待人工复审")
    print(f"\n✅ 翻案抽查完成")

if __name__ == "__main__":
    resample()
