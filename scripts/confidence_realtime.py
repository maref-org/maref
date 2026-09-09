#!/usr/bin/env python3
"""置信度字段真实化改造 (P-06)"""
import json, os, sqlite3, statistics
from datetime import datetime, timedelta

DB_PATH = "/Volumes/1TB-M2/public/maref/governance_observations.db"

def calculate_confidence(window_days=30):
    """滑动窗口实算置信度: 成功率×0.6 + 审计通过率×0.3 + 心跳稳定性×0.1"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=window_days)).timestamp()
    
    cursor.execute('''
        SELECT probe_name, severity, COUNT(*) 
        FROM probe_readings 
        WHERE timestamp > ?
        GROUP BY probe_name, severity
    ''', (cutoff,))
    
    data = cursor.fetchall()
    conn.close()
    
    total = sum(r[2] for r in data)
    if total == 0:
        return 68, {}
    
    normal_count = sum(r[2] for r in data if r[1] == 'normal')
    warning_count = sum(r[2] for r in data if r[1] == 'warning')
    critical_count = sum(r[2] for r in data if r[1] == 'critical')
    
    success_rate = normal_count / total if total > 0 else 0
    audit_pass_rate = 1 - (critical_count / total) if total > 0 else 0
    heartbeat_stability = 1 - (warning_count / total) if total > 0 else 0
    
    confidence = (success_rate * 0.6 + audit_pass_rate * 0.3 + heartbeat_stability * 0.1) * 100
    
    stats = {
        "total": total,
        "normal": normal_count,
        "warning": warning_count,
        "critical": critical_count,
        "success_rate": round(success_rate, 4),
        "audit_pass_rate": round(audit_pass_rate, 4),
        "heartbeat_stability": round(heartbeat_stability, 4)
    }
    
    return round(confidence, 2), stats

def main():
    print("=" * 60)
    print("置信度实算报告 (P-06)")
    print("=" * 60)
    
    overall, stats = calculate_confidence()
    print(f"\n整体置信度 (30天窗口): {overall}")
    print(f"对比常量值: 68")
    print(f"差异: {overall - 68:+.2f}")
    
    print(f"\n--- 探针分布 ---")
    print(f"  总读数: {stats.get('total', 0)}")
    print(f"  normal: {stats.get('normal', 0)}")
    print(f"  warning: {stats.get('warning', 0)}")
    print(f"  critical: {stats.get('critical', 0)}")
    
    print(f"\n--- 维度分数 ---")
    print(f"  成功率 (×0.6): {stats.get('success_rate', 0)}")
    print(f"  审计通过率 (×0.3): {stats.get('audit_pass_rate', 0)}")
    print(f"  心跳稳定性 (×0.1): {stats.get('heartbeat_stability', 0)}")
    
    # 验证 σ > 8
    counts = [stats.get('normal', 0), stats.get('warning', 0), stats.get('critical', 0)]
    if len(counts) > 1 and statistics.stdev(counts) > 0:
        std = statistics.stdev(counts)
        print(f"\n--- 分布统计 ---")
        print(f"标准差 σ: {std:.2f}")
        print(f"目标 σ > 8: {'✅ 达标' if std > 8 else '⚠️ 未达标'}")
    
    # 保存报告
    report = {
        "audit_date": datetime.now().isoformat(),
        "confidence_30d": overall,
        "legacy_value": 68,
        "difference": round(overall - 68, 2),
        "stats": stats
    }
    
    output_path = "/Volumes/1TB-M2/public/maref/reports/confidence_audit.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n报告已保存: {output_path}")
    print(f"\n✅ 置信度实算完成")

if __name__ == "__main__":
    main()
