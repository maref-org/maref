#!/usr/bin/env python3
"""置信度字段真实化改造 (P-06) — 使用重校准阈值"""
import json
import os
import sqlite3
import statistics
from datetime import datetime, timedelta

from maref_config import PROBE_DB as DB_PATH
from maref_config import config_path, report_path

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

# T2-3: reverse 探针规则 (与 probe_sampler 默认阈值一致: 越高越好)
REVERSE_RULES = {
    "governance_health": {"critical_min": 50.0, "normal_min": 80.0},
    "agent_trust": {"critical_min": 40.0, "normal_min": 70.0},
}


def _reclassify(probe_name: str, value: float, thresholds: dict) -> str | None:
    """T2-3 回放重分类: 校准配置(分位数) / reverse 规则重判 severity。

    返回 None = 假分排除 (T1-6 修复前无数据写 0 的读数, 不计入统计);
    返回 "use_stored" = 该探针无配置, 沿用采样器已存 severity。
    """
    rule = REVERSE_RULES.get(probe_name)
    if rule is not None:
        if value <= 0:
            return None
        if value < rule["critical_min"]:
            return "critical"
        if value < rule["normal_min"]:
            return "warning"
        return "normal"
    p = (thresholds.get("probes") or {}).get(probe_name)
    if p:
        if value > float(p["critical_min"]):
            return "critical"
        if value > float(p["normal_max"]):
            return "warning"
        return "normal"
    return "use_stored"

def calculate_confidence(window_days=30):
    thresholds = load_thresholds()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=window_days)).timestamp()
    cursor.execute(
        "SELECT probe_name, severity, value FROM probe_readings "
        "WHERE probe_name != 'test' AND timestamp > ?",
        (cutoff,),
    )
    rows = cursor.fetchall()
    conn.close()

    normal_count = 0
    warning_count = 0
    critical_count = 0
    excluded_no_data = 0

    # T2-3: 校准配置存在时按阈值回放重分类 (历史读数由旧阈值分类,
    # 重标定后必须回放才能反映真实分布); 无配置时沿用已存 severity
    # (采样器=单一裁决源, L4)。reverse 探针的 value<=0 假分始终排除。
    for probe_name, sev, value in rows:
        if thresholds:
            new_sev = _reclassify(probe_name, value, thresholds)
            if new_sev is None:
                excluded_no_data += 1
                continue
            if new_sev != "use_stored":
                sev = new_sev
        elif probe_name in REVERSE_RULES and value <= 0:
            excluded_no_data += 1
            continue
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
        "excluded_no_data": excluded_no_data,
        "reclassified": bool(thresholds),
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
    print("对比常量值: 68")
    print(f"差异: {overall - 68:+.2f}")
    print("分类源: 校准阈值回放重分类 (T2-3) + reverse 规则; 假分已排除")

    print("\n--- 探针分布 (重校准后) ---")
    print(f"  总读数: {stats.get('total', 0)}")
    print(f"  normal: {stats.get('normal', 0)}")
    print(f"  warning: {stats.get('warning', 0)}")
    print(f"  critical: {stats.get('critical', 0)}")

    print("\n--- 维度分数 ---")
    print(f"  成功率 (×0.6): {stats.get('success_rate', 0)}")
    print(f"  审计通过率 (×0.3): {stats.get('audit_pass_rate', 0)}")
    print(f"  心跳稳定性 (×0.1): {stats.get('heartbeat_stability', 0)}")

    counts = [stats.get("normal", 0), stats.get("warning", 0), stats.get("critical", 0)]
    if len(counts) > 1 and statistics.stdev(counts) > 0:
        std = statistics.stdev(counts)
        print("\n--- 分布统计 ---")
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
    print("\n✅ 置信度实算完成")

if __name__ == "__main__":
    main()
