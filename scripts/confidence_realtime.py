#!/usr/bin/env python3
"""置信度字段真实化改造 (P-06) — 使用重校准阈值"""
import json
import os
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone

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

def calculate_confidence(window_days=30):
    thresholds = load_thresholds()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=window_days)).timestamp()
    cursor.execute(
        "SELECT probe_name, severity, value, timestamp, context_json FROM probe_readings "
        "WHERE probe_name != 'test' AND timestamp > ? "
        "AND CASE WHEN json_valid(context_json) "
        "THEN json_extract(context_json, '$.source') END = 'probe_sampler_v3' "
        "ORDER BY timestamp",
        (cutoff,),
    )
    rows = cursor.fetchall()
    conn.close()

    # 同一探针每天只取最后一次采样，避免采样频率差异扭曲分布。
    latest: dict[tuple[object, str], tuple[str, float, dict]] = {}
    for probe_name, sev, value, ts, context_json in rows:
        day = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
        try:
            ctx = json.loads(context_json or "{}")
        except json.JSONDecodeError:
            ctx = {}
        latest[(day, probe_name)] = (sev, float(value), ctx)

    probes = (thresholds or {}).get("probes", {})
    normal_count = 0
    warning_count = 0
    critical_count = 0
    excluded_low_sample = 0

    for (_day, probe_name), (stored_sev, value, ctx) in latest.items():
        sample = ctx.get("window_used")
        if sample is None:
            sample = ctx.get("tool_calls_total")
        if sample is not None and float(sample) < 10:
            excluded_low_sample += 1
            continue
        if probe_name == "agent_trust" and ctx.get("agents_with_data", 1) == 0:
            excluded_low_sample += 1
            continue
        t = probes.get(probe_name) or {}
        if probe_name in ("oscillation", "entropy") and t:
            if value <= t.get("normal_max", float("inf")):
                sev = "normal"
            elif value >= t.get("critical_min", float("inf")):
                sev = "critical"
            else:
                sev = "warning"
        elif t:
            normal_min = t.get("normal_min", 80.0 if probe_name == "governance_health" else 70.0)
            critical_min = t.get("critical_min", 50.0 if probe_name == "governance_health" else 40.0)
            if value >= normal_min:
                sev = "normal"
            elif value < critical_min:
                sev = "critical"
            else:
                sev = "warning"
        else:
            # 无当前阈值时保留采样时的分类，避免把未知探针误判为健康。
            sev = stored_sev
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
        "aggregation": "daily_latest_per_probe",
        "window_days": window_days,
        "source": "probe_sampler_v3",
        "excluded_low_sample": excluded_low_sample,
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
    print("分类源: 当前阈值重分类 (probe_sampler_v3, 日级最新值, 低样本剔除)")

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
