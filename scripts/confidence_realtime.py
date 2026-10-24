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
MIN_WINDOW_SAMPLES = 10   # 单日采样窗口少于该值视为低样本，剔除
MIN_DEGENERATE_SAMPLES = 5  # 日级样本达到该数量且取值恒定 ⇒ 退化探针
SUSPICIOUS_SCALE_RATIO = 5.0  # 中位数与阈值相差该倍数 ⇒ 疑似阈值尺度失配


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).timestamp()
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
    unknown_count = 0
    excluded_low_sample = 0
    excluded_degenerate = 0

    # 退化探针：30 天日级取值恒定 ⇒ 零信息量（如熵探针恒 57.9）。
    # 这种读数无论阈值如何都只会给指标灌水，不能作为健康证据。
    per_probe_values: dict[str, set[float]] = {}
    per_probe_days: dict[str, int] = {}
    for (_day, probe_name), (_sev, value, _ctx) in latest.items():
        per_probe_values.setdefault(probe_name, set()).add(value)
        per_probe_days[probe_name] = per_probe_days.get(probe_name, 0) + 1
    degenerate = {
        name for name, vals in per_probe_values.items()
        if len(vals) == 1 and per_probe_days.get(name, 0) >= MIN_DEGENERATE_SAMPLES
    }

    # 阈值尺度失配检测：探针读数与阈值长期差一个量级（典型症状：探针单位从
    # 绝对值改成百分比后，阈值仍沿用旧量级 → 读数恒 critical/normal）。
    # 只告警、不改判，避免脚本替人做治理决策。
    suspicious: dict[str, dict[str, float]] = {}
    for name, vals in per_probe_values.items():
        t = probes.get(name) or {}
        if per_probe_days.get(name, 0) < MIN_DEGENERATE_SAMPLES or not t:
            continue
        median = statistics.median(vals)
        if name in ("oscillation", "entropy"):
            crit = float(t.get("critical_min") or 0)
            if crit > 0:
                ratio = median / crit
                # 只告警"读数长期远高于危险阈值"（单位放大症状）；
                # 长期贴近 0 属正常静默，不应触发。
                if ratio >= SUSPICIOUS_SCALE_RATIO:
                    suspicious[name] = {"median": median, "critical_min": crit, "ratio": round(ratio, 2)}
        else:
            crit = float(t.get("critical_min") or 0)
            if crit > 0 and 0 < median < crit / SUSPICIOUS_SCALE_RATIO:
                suspicious[name] = {"median": median, "critical_min": crit, "ratio": round(median / crit, 2)}

    for (_day, probe_name), (stored_sev, value, ctx) in latest.items():
        if probe_name in degenerate:
            excluded_degenerate += 1
            continue
        try:
            sample = ctx.get("window_used")
            if sample is None:
                sample = ctx.get("tool_calls_total")
            sample_value = float(sample) if sample is not None else None
        except (TypeError, ValueError):
            sample_value = None
        if sample_value is not None and sample_value < MIN_WINDOW_SAMPLES:
            excluded_low_sample += 1
            continue
        if probe_name == "agent_trust" and _as_int(ctx.get("agents_with_data"), 1) == 0:
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
        elif sev == "critical":
            critical_count += 1
        else:
            # 未知分类保守计入 critical，但单独计数以便暴露数据问题
            unknown_count += 1
            critical_count += 1

    total = normal_count + warning_count + critical_count
    if total == 0:
        # 无有效样本：返回先验并显式标记，避免"静默等于健康"
        return PRIOR_CONFIDENCE * 100, {
            "total": 0,
            "fallback": "prior_no_samples",
            "excluded_low_sample": excluded_low_sample,
            "excluded_degenerate": excluded_degenerate,
            "degenerate_probes": sorted(degenerate),
        }, thresholds is not None

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
        "excluded_degenerate": excluded_degenerate,
        "degenerate_probes": sorted(degenerate),
        "suspicious_probes": suspicious,
        "unknown_severity": unknown_count,
        "fallback": None,
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
    print("分类源: 当前阈值重分类 (probe_sampler_v3, 日级最新值, 低样本/退化探针剔除)")

    if stats.get("fallback"):
        print(f"\n⚠️ 无有效样本，回退先验 {PRIOR_CONFIDENCE * 100:.0f} ({stats['fallback']})")
    if stats.get("degenerate_probes"):
        print(f"⚠️ 退化探针 (取值恒定, 已剔除): {', '.join(stats['degenerate_probes'])}")
    for name, info in (stats.get("suspicious_probes") or {}).items():
        print(f"⚠️ 阈值尺度失配: {name} 中位数={info['median']} vs critical_min={info['critical_min']}"
              f" (×{info['ratio']}) — 读数可信度存疑，请重新校准阈值")
    if stats.get("excluded_low_sample"):
        print(f"ℹ️ 低样本剔除: {stats['excluded_low_sample']}")
    if stats.get("excluded_degenerate"):
        print(f"ℹ️ 退化剔除: {stats['excluded_degenerate']}")
    if stats.get("unknown_severity"):
        print(f"ℹ️ 未知分类(保守计入 critical): {stats['unknown_severity']}")

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
        "audit_date": datetime.now(timezone.utc).isoformat(),
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
