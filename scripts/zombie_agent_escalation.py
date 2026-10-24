#!/usr/bin/env python3
"""僵死 Agent 自动升级 (P-04)"""
import json, os, sqlite3
from datetime import datetime, timedelta
from maref_config import PROBE_DB as DB_PATH, AUDIT_LOG, config_path, report_path

WEIGHTS_FILE = config_path("agent_domain_weights.json")

def load_weights():
    if not os.path.exists(WEIGHTS_FILE):
        return {"default": 1}
    with open(WEIGHTS_FILE) as f:
        return json.load(f)

def detect_zombie_agents():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(hours=24)).timestamp()
    cursor.execute('''
        SELECT probe_name, severity, COUNT(*), MAX(timestamp)
        FROM probe_readings
        WHERE probe_name != 'test'
        GROUP BY probe_name
    ''')

    results = cursor.fetchall()
    conn.close()

    weights = load_weights()
    zombies = []

    for probe_name, severity, count, last_ts in results:
        has_critical = severity == 'critical'
        stale = (last_ts and last_ts < cutoff)

        if stale or (has_critical and count > 100):
            weight = weights.get(probe_name, weights.get("default", 1))
            zombies.append({
                "agent": probe_name,
                "severity": severity,
                "count": count,
                "last_seen": datetime.fromtimestamp(last_ts).isoformat() if last_ts else "never",
                "domain_weight": weight,
                "stale": stale,
                "proposal": "restart" if stale else "health_check"
            })

    return zombies

def main():
    print("=" * 60)
    print("僵死 Agent 检测报告 (P-04)")
    print("=" * 60)

    zombies = detect_zombie_agents()

    if not zombies:
        print("\n未检测到僵死 Agent")
        return

    print(f"\n检测到 {len(zombies)} 个需关注的 Agent:\n")

    for z in sorted(zombies, key=lambda x: -x['domain_weight']):
        weight_level = {4: "constitutional", 3: "orchestrator", 2: "service", 1: "leaf"}[z['domain_weight']]
        alert = "域级告警" if z['domain_weight'] >= 3 else "温和提示"
        print(f"  [{alert}] {z['agent']} (weight={z['domain_weight']}, {weight_level})")
        print(f"    状态: {z['severity']}, 计数: {z['count']}, 最后活跃: {z['last_seen']}")
        print(f"    建议处置: {z['proposal']}")
        print()

    output_path = str(report_path("zombie_agent_report.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({
            "scan_date": datetime.now().isoformat(),
            "zombie_count": len(zombies),
            "zombies": zombies
        }, f, indent=2, ensure_ascii=False)
    print(f"报告已保存: {output_path}")

if __name__ == "__main__":
    main()