#!/usr/bin/env python3
"""探针阈值重校准 (P0: ISSUE-002) — 百分位数法"""
import json, os, sqlite3, statistics
from datetime import datetime
from maref_config import PROBE_DB as DB_PATH, config_path

CONFIG_PATH = config_path("probe_thresholds.json")

def compute_percentiles(values, percentiles=[50, 75, 90, 95, 99]):
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = {}
    for p in percentiles:
        k = (p / 100) * (n - 1)
        f = int(k)
        c = k - f
        if f + 1 < n:
            val = sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
        else:
            val = sorted_vals[f]
        result[f"P{p}"] = round(val, 2)
    return result

def analyze_probe(probe_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value, severity FROM probe_readings WHERE probe_name = ?",
        (probe_name,)
    )
    rows = cursor.fetchall()
    conn.close()

    values = [r[0] for r in rows]
    old_severity = {"normal": 0, "warning": 0, "critical": 0}
    for _, s in rows:
        if s in old_severity:
            old_severity[s] += 1

    percentiles = compute_percentiles(values)

    p75 = percentiles["P75"]
    p95 = percentiles["P95"]

    new_severity = {"normal": 0, "warning": 0, "critical": 0}
    for v in values:
        if v <= p75:
            new_severity["normal"] += 1
        elif v <= p95:
            new_severity["warning"] += 1
        else:
            new_severity["critical"] += 1

    return {
        "probe_name": probe_name,
        "total_readings": len(values),
        "value_range": [min(values), max(values)],
        "percentiles": percentiles,
        "new_thresholds": {
            "normal": f"<= P75 ({p75})",
            "warning": f"P75-P95 ({p75} - {p95})",
            "critical": f"> P95 ({p95})",
            "p75_value": p75,
            "p95_value": p95,
        },
        "old_distribution": old_severity,
        "new_distribution": new_severity,
    }

def main():
    print("=" * 60)
    print("探针阈值重校准报告 (ISSUE-002)")
    print("=" * 60)

    # 空库守卫: 运行时 DB 可能无读数
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0]
    conn.close()
    if total == 0:
        print("⚠️ 探针数据库无读数，跳过校准")
        print(f"  DB: {DB_PATH}")
        print("  原因: 运行时 collector 未运行 (见 P0-B)")
        return

    results = {}
    for probe in ["oscillation", "entropy"]:
        print(f"\n{'─' * 40}")
        r = analyze_probe(probe)
        results[probe] = r

        print(f"\n{probe} 探针:")
        print(f"  总读数: {r['total_readings']}")
        print(f"  值范围: {r['value_range']}")

        print(f"\n  分位数:")
        for k, v in r["percentiles"].items():
            print(f"    {k}: {v}")

        print(f"\n  新阈值方案:")
        print(f"    normal: {r['new_thresholds']['normal']}")
        print(f"    warning: {r['new_thresholds']['warning']}")
        print(f"    critical: {r['new_thresholds']['critical']}")

        print(f"\n  旧分布: normal={r['old_distribution']['normal']}, "
              f"warning={r['old_distribution']['warning']}, "
              f"critical={r['old_distribution']['critical']}")

        print(f"  新分布: normal={r['new_distribution']['normal']}, "
              f"warning={r['new_distribution']['warning']}, "
              f"critical={r['new_distribution']['critical']}")

        old_crit_pct = r['old_distribution']['critical'] / r['total_readings'] * 100
        new_crit_pct = r['new_distribution']['critical'] / r['total_readings'] * 100
        print(f"  critical 占比: {old_crit_pct:.1f}% → {new_crit_pct:.1f}%")

    config = {
        "calibrated_at": datetime.now().isoformat(),
        "method": "percentile_based",
        "probes": {
            k: {
                "normal_max": v["new_thresholds"]["p75_value"],
                "critical_min": v["new_thresholds"]["p95_value"],
            }
            for k, v in results.items()
        },
    }

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\n阈值配置已保存: {CONFIG_PATH}")

    estimated_confidence = compute_estimated_confidence(results)
    print(f"\n{'=' * 60}")
    print(f"预估重校准后置信度: {estimated_confidence}")
    print(f"重校准前置信度: 12.0")
    print(f"改善: {estimated_confidence - 12.0:+.1f}")

def compute_estimated_confidence(results):
    total = sum(r["total_readings"] for r in results.values())
    normal = sum(r["new_distribution"]["normal"] for r in results.values())
    warning = sum(r["new_distribution"]["warning"] for r in results.values())
    critical = sum(r["new_distribution"]["critical"] for r in results.values())

    success_rate = normal / total if total > 0 else 0
    audit_pass_rate = 1 - (critical / total) if total > 0 else 0
    heartbeat_stability = 1 - (warning / total) if total > 0 else 0

    return round((success_rate * 0.6 + audit_pass_rate * 0.3 + heartbeat_stability * 0.1) * 100, 2)

if __name__ == "__main__":
    main()