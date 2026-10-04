#!/usr/bin/env python3
"""审计日志 schema 补丁 (P1: ISSUE-001) — 解析 verdict/risk_level 回填"""
import json
import os
from datetime import datetime

from maref_config import (
    AUDIT_LOG,
    report_path,
)
from maref_config import (
    AUDIT_LOG_V2 as OUTPUT_AUDIT,
)
from maref_config import (
    RECURSIVE_AUDIT_LOG as RECURSIVE_LOG,
)
from maref_config import (
    RECURSIVE_AUDIT_LOG_V2 as OUTPUT_RECURSIVE,
)


def parse_verdict(details, action=""):
    if not details:
        return "unknown"
    upper = details.upper()
    if upper.startswith("ALLOW"):
        verdict = "allow"
    elif upper.startswith("DENY"):
        verdict = "deny"
    elif upper.startswith("ASK_USER") or "entropy" in details.lower():
        verdict = "flag"
    elif "initial" in details.lower() or "desktop" in details.lower():
        verdict = "allow"
    else:
        # T2-1: action 规则兜底（details 不可解析时）
        if action.split(":")[0] == "governance_bypassed":
            verdict = "flag"  # 治理绕过必须人工复核
        elif action in ("oscillation_intervention", "force_stabilize",
                        "auto_transition", "state_transition"):
            verdict = "allow"  # 可逆稳定化干预
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
            except Exception:
                pass

    patched = []
    stats = {"verdict": {}, "risk_level": {}, "total": len(entries)}

    for entry in entries:
        details = entry.get("details", "")
        if isinstance(details, dict):
            details = json.dumps(details)
        action = entry.get("action", "")

        verdict = parse_verdict(details, action)
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
        print("  verdict 分布:")
        for k, v in sorted(stats["verdict"].items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")
        print("  risk_level 分布:")
        for k, v in sorted(stats["risk_level"].items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")
        print(f"  输出: {output}")

    print("\n--- 批复章示 ---")
    print(f"原日志路径: {AUDIT_LOG} / {RECURSIVE_LOG}")
    print(f"补丁后路径: {OUTPUT_AUDIT} / {OUTPUT_RECURSIVE}")
    print("原日志未修改，补丁输出为独立文件")
    print("后续脚本应使用 v2 路径或通过符号链接切换")

    output_path = str(report_path("schema_patch_report.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "patch_date": datetime.now().isoformat(),
            "original_files": [str(AUDIT_LOG), str(RECURSIVE_LOG)],
            "patched_files": [str(OUTPUT_AUDIT), str(OUTPUT_RECURSIVE)],
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
