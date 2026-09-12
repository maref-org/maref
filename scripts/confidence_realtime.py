#!/usr/bin/env python3
"""置信度字段真实化改造 (P-06) — 使用重校准阈值"""
import json, os, sqlite3, statistics
from datetime import datetime, timedelta
from maref_config import PROBE_DB as DB_PATH, config_path, report_path

THRESHOLD_PATH = config_path("probe_thresholds.json")

# L3: 样本量感知平滑 — 小样本向先验收缩，避免 n=2 时饱和到 100%
PRIOR_CONFIDENCE = 0.68   # 先验 = legacy 常量 68/100
PRIOR_STRENGTH = 20.0     # 伪计数 (越大越向先验收缩, 越小越信观测)


def _smooth(positive: float, total: float, prior: float = PRIOR_CONFIDENCE,
            k: float = PRIOR_STRENGTH) -> float:
    """贝叶斯收缩：(positive + k·prior) / (total + k)。

    小样本 → 接近先验；大样本 → 接近观测值。消除小样本饱和问题。
    """
    return (positive + k * prior) / (total + k)

def load_thresholds():
    if os.path.exists(THRESHOLD_PATH):
        with open(THRESHOLD_PATH) as f:
            return json.load(f)
    return None

def calculate_confidence(window_days=30):
    thresholds = load_thresholds()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=window_days)).timestamp()
    cursor.execute(
        "SELECT probe_name, severity FROM probe_readings "
        "WHERE probe_name != 'test' AND timestamp > ?",
        (cutoff,),
    )
    rows = cursor.fetchall()
    conn.close()

    normal_count = 0
    warning_count = 0
    critical_count = 0

    # L4: 直接聚合已存 severity (采样器=分类器, 单一裁决源)
    # 不再重分类, 避免与采样器阈值冲突/双重分类。
    for _probe_name, sev in rows:
        if sev == "normal":
            normal_count += 1
        elif sev == "warning":
            warning_count += 1
        else:
            critical_count += 1

    total = normal_count + warning_count + critical_count
    if total == 0:
        return 68, {}, False

    success_rate = _smooth(normal_count, total)
    audit_pass_rate = _smooth(total - critical_count, total)
    heartbeat_stability = _smooth(total - warning_count, total)

    confidence = (success_rate * 0.6 + audit_pass_rate * 0.3 + heartbeat_stability * 0.1) * 100

    stats = {
        "total": total,
        "normal": normal_count,
        "warning": warning_count,
        "critical": critical_count,
        "success_rate": round(success_rate, 4),
        "audit_pass_rate": round(audit_pass_rate, 4),
        "heartbeat_stability": round(heartbeat_stability, 4),
        "calibrated": thresholds is not None,
        "smoothed": True,
        "prior_strength": PRIOR_STRENGTH,
        "prior_confidence": PRIOR_CONFIDENCE,
    }

    return round(confidence, 2), stats, thresholds is not None

def main():
    print("=" * 60)
    print("置信度实算报告 (P-06) — 重校准阈值")
    print("=" * 60)

    overall, stats, calibrated = calculate_confidence()

    print(f"\n整体置信度 (30天窗口): {overall}")
    print(f"对比常量值: 68")
    print(f"差异: {overall - 68:+.2f}")
    print(f"分类源: 已存 severity (采样器为单一分类器)")

    print(f"\n--- 探针分布 (重校准后) ---")
    print(f"  总读数: {stats.get('total', 0)}")
    print(f"  normal: {stats.get('normal', 0)}")
    print(f"  warning: {stats.get('warning', 0)}")
    print(f"  critical: {stats.get('critical', 0)}")

    print(f"\n--- 维度分数 ---")
    print(f"  成功率 (×0.6): {stats.get('success_rate', 0)}")
    print(f"  审计通过率 (×0.3): {stats.get('audit_pass_rate', 0)}")
    print(f"  心跳稳定性 (×0.1): {stats.get('heartbeat_stability', 0)}")

    counts = [stats.get("normal", 0), stats.get("warning", 0), stats.get("critical", 0)]
    if len(counts) > 1 and statistics.stdev(counts) > 0:
        std = statistics.stdev(counts)
        print(f"\n--- 分布统计 ---")
        print(f"标准差 σ: {std:.2f}")
        print(f"目标 σ > 8: {'✅ 达标' if std > 8 else '⚠️ 未达标'}")

    report = {
        "audit_date": datetime.now().isoformat(),
        "confidence_30d": overall,
        "legacy_value": 68,
        "difference": round(overall - 68, 2),
        "calibrated": calibrated,
        "stats": stats,
    }

    output_path = str(report_path("confidence_audit.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n报告已保存: {output_path}")
    print(f"\n✅ 置信度实算完成")

if __name__ == "__main__":
    main()