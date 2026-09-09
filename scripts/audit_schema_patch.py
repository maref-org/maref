#!/usr/bin/env python3
"""审计日志 schema 补丁 (P1: ISSUE-001) — 解析 verdict/risk_level 回填"""
import json, os, re
from datetime import datetime

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit.jsonl"
RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit.jsonl"
OUTPUT_AUDIT = "/Volumes/1TB-M2/public/maref/governance_audit_v2.jsonl"
OUTPUT_RECURSIVE = "/Volumes/1TB-M2/public/maref/recursive_governance_audit_v2.jsonl"

def parse_verdict(details):
    if not details:
        return "unknown"
    upper = details.upper()
    if upper.startswith("ALLOW"):
        verdict = "allow"
    elif upper.startswith("DENY"):
        verdict = "deny"
    elif upper.startswith("ASK_USER"):
        verdict = "flag"
    elif "entropy" in details.lower():
        verdict = "flag"
    elif "initial" in details.lower() or "desktop" in details.lower():
        verdict = "allow"
    else:
        verdict = "unknown"
    return verdict

def parse_risk_level(details, verdict, action):
    if not details:
        return "unknown"
    upper = details.upper()
    if "IRREVERSIBLE" in upper:
        return "irreversible"
    if verdict == "deny":
        return "high"
    if verdict == "flag":
        return "medium"
    if "mouse" in details.lower() or "keyboard" in details.lower():
        return "medium"
    if verdict == "allow":
        return "low"
    return "unknown"

def patch_log(input_path, output_path, source_name):
    entries = []
    with open(input_path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                pass

    patched = []
    stats = {"verdict": {}, "risk_level": {}, "total": len(entries)}

    for entry in entries:
        details = entry.get("details", "")
        if isinstance(details, dict):
            details = json.dumps(details)
        action = entry.get("action", "")

        verdict = parse_verdict(details)
        risk_level = parse_risk_level(details, verdict, action)

        entry["verdict"] = verdict
        entry["risk_level"] = risk_level
        stats["verdict"][verdict] = stats["verdict"].get(verdict, 0) + 1
        stats["risk_level"][risk_level] = stats["risk_level"].get(risk_level, 0) + 1
        patched.append(entry)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for entry in patched:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return stats, patched

def main():
    print("=" * 60)
    print("审计日志 schema 补丁 (P1: ISSUE-001)")
    print("=" * 60)

    for path, output, name in [
        (AUDIT_LOG, OUTPUT_AUDIT, "governance_audit"),
        (RECURSIVE_LOG, OUTPUT_RECURSIVE, "recursive_governance_audit"),
    ]:
        stats, patched = patch_log(path, output, name)
        print(f"\n--- {name} ---")
        print(f"总条目: {stats['total']}")
        print(f"  verdict 分布:")
        for k, v in sorted(stats["verdict"].items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")
        print(f"  risk_level 分布:")
        for k, v in sorted(stats["risk_level"].items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")
        print(f"  输出: {output}")

    print(f"\n--- 批复章示 ---")
    print(f"原日志路径: {AUDIT_LOG} / {RECURSIVE_LOG}")
    print(f"补丁后路径: {OUTPUT_AUDIT} / {OUTPUT_RECURSIVE}")
    print(f"原日志未修改，补丁输出为独立文件")
    print(f"后续脚本应使用 v2 路径或通过符号链接切换")

    output_path = "/Volumes/1TB-M2/public/maref/reports/schema_patch_report.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "patch_date": datetime.now().isoformat(),
            "original_files": [AUDIT_LOG, RECURSIVE_LOG],
            "patched_files": [OUTPUT_AUDIT, OUTPUT_RECURSIVE],
            "verdict_rules": {
                "ALLOW:*": "allow",
                "DENY:*": "deny",
                "ASK_USER:*": "flag",
                "entropy detected": "flag",
                "initial/desktop": "allow",
            },
            "risk_rules": {
                "IRREVERSIBLE": "irreversible",
                "deny": "high",
                "flag": "medium",
                "mouse/keyboard": "medium",
                "allow": "low",
            },
        }, f, indent=2, ensure_ascii=False)
    print(f"\n补丁报告已保存: {output_path}")

if __name__ == "__main__":
    main()