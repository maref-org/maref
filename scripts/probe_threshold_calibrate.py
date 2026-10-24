#!/usr/bin/env python3
"""探针阈值重校准 (P0: ISSUE-002) — 百分位数法

产物：
- configs/probe_thresholds.json   生效阈值
- reports/calibration_artifact.json 校准证据（样本量/分位表/DB 指纹/config hash）

证据链：artifact 绑定 config 的具体数值，任何手改 config 都会在
`--verify` 时与 artifact 不一致（这是此前 444→10.1 无法追溯的根因）。
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from maref_config import PROBE_DB as DB_PATH
from maref_config import config_path, report_path

CONFIG_PATH = config_path("probe_thresholds.json")
ARTIFACT_PATH = report_path("calibration_artifact.json")

# L4: 小样本守卫 — 样本不足时分位数退化 (P75≈P95)，会产出无效阈值
MIN_SAMPLES = 24

def _db_fingerprint() -> dict:
    """DB 指纹：让阈值可追溯到具体数据快照。"""
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    row = None
    if size:
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(timestamp) FROM probe_readings"
            ).fetchone()
        except sqlite3.DatabaseError:
            row = None  # 空文件或未初始化 schema
        finally:
            conn.close()
    return {
        "path": str(DB_PATH),
        "size_bytes": size,
        "readings": row[0] if row else 0,
        "max_timestamp": row[1] if row else None,
    }


def _sha256_of(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> int:
    """校验当前 config 与最近一次校准 artifact 是否一致（防手改）。"""
    if not os.path.exists(ARTIFACT_PATH):
        print(f"❌ 无校准 artifact: {ARTIFACT_PATH}")
        return 2
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 无阈值配置: {CONFIG_PATH}")
        return 2
    with open(ARTIFACT_PATH) as fh:
        artifact = json.load(fh)
    with open(CONFIG_PATH) as fh:
        config = json.load(fh)

    provenance = artifact.get("provenance", "percentile_based")
    if provenance != "percentile_based":
        print(f"⚠️ 校准产物 provenance={provenance}，当前阈值未经数据校准"
              f"（reason: {artifact.get('reason', 'n/a')}）")

    expected = artifact.get("config", {})
    ok = True
    exp_probes = expected.get("probes", {})
    got_probes = config.get("probes", {})
    for name in sorted(set(exp_probes) | set(got_probes)):
        if exp_probes.get(name) != got_probes.get(name):
            ok = False
            print(f"❌ 阈值与校准 artifact 不一致: {name} "
                  f"artifact={exp_probes.get(name)} config={got_probes.get(name)}")
    if artifact.get("config_sha256") != _sha256_of(CONFIG_PATH):
        print("ℹ️ config 文件哈希与校准产物不同（格式化或人工编辑）")

    db = artifact.get("db") or {}
    current = _db_fingerprint()
    if db.get("max_timestamp") != current["max_timestamp"]:
        print(f"ℹ️ DB 已有新样本 (artifact max_ts={db.get('max_timestamp')}, "
              f"current={current['max_timestamp']})，建议重新校准")

    if ok:
        print(f"✅ 阈值配置与校准产物一致: {CONFIG_PATH}")
        return 0
    return 1


def compute_percentiles(values, percentiles=None):
    percentiles = percentiles or [50, 75, 90, 95, 99]
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

def _degenerate_reason(p75: float, p95: float) -> str | None:
    """判断分位阈值是否退化（无从分辨正常/异常）。"""
    if p75 <= 0:
        return f"P75={p75} ≤ 0，正常区间退化为单点（窗口内多为无事件读数）"
    if p95 <= p75:
        return f"P75=P95={p75}，≥25% 样本聚集在同一值，分位法无分辨力"
    return None


def analyze_probe(probe_name, since_ts: float | None = None, source: str | None = None):
    """按探针计算分位数。

    since_ts/source 用于排除历史口径（例如旧版绝对熵值混入 v3 百分比数据），
    否则分位阈值会落在两套语义之间而完全不可用。
    """
    sql = "SELECT value, severity FROM probe_readings WHERE probe_name = ?"
    params: list[object] = [probe_name]
    if since_ts is not None:
        sql += " AND timestamp > ?"
        params.append(since_ts)
    if source:
        sql += " AND json_extract(context_json, '$.source') = ?"
        params.append(source)

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    values = [r[0] for r in rows]
    old_severity = {"normal": 0, "warning": 0, "critical": 0}
    for _, s in rows:
        if s in old_severity:
            old_severity[s] += 1

    percentiles = compute_percentiles(values)

    p75 = percentiles["P75"]
    p95 = percentiles["P95"]
    degenerate_reason = _degenerate_reason(p75, p95)

    # L4: 非退化守卫 — 若 P95 ≤ P75 (全等值)，加最小间隔防正常/危险同阈
    if p95 <= p75:
        p95 = p75 + max(1.0, p75 * 0.1)

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
        "degenerate_reason": degenerate_reason,
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

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探针阈值重校准（百分位数法）")
    parser.add_argument("--verify", action="store_true", help="仅校验 config 与校准产物是否一致")
    parser.add_argument(
        "--window-days", type=int, default=0,
        help="只用最近 N 天样本（0 = 全量，默认保持旧行为）",
    )
    parser.add_argument(
        "--source", default="",
        help="只统计指定 ctx.source（如 probe_sampler_v3），避免历史口径混入",
    )
    parser.add_argument(
        "--accept-seed", action="store_true",
        help="为现有阈值写 seed artifact（明确标记未经数据校准），供 --verify 通过",
    )
    parser.add_argument("--reason", default="", help="seed artifact 的说明")
    return parser.parse_args(argv)


def _write_seed_artifact(reason: str) -> int:
    """把现有 config 记录为 seed：可追溯，但不假装是分位校准结果。"""
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 无阈值配置: {CONFIG_PATH}")
        return 2
    with open(CONFIG_PATH) as fh:
        config = json.load(fh)
    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "seed_uncalibrated",
        "reason": reason or "分位校准不可行（数据退化），沿用现有阈值",
        "config_path": str(CONFIG_PATH),
        "config_sha256": _sha256_of(CONFIG_PATH),
        "config": config,
        "db": _db_fingerprint(),
        "per_probe": None,
        "script": os.path.basename(__file__),
    }
    os.makedirs(os.path.dirname(ARTIFACT_PATH), exist_ok=True)
    with open(ARTIFACT_PATH, "w") as fh:
        json.dump(artifact, fh, indent=2, ensure_ascii=False)
    print(f"⚠️ 已写入 seed artifact（未校准）: {ARTIFACT_PATH}")
    print(f"   reason: {artifact['reason']}")
    return 0


def main(argv: list[str] | None = None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    since_ts = (
        (datetime.now(timezone.utc) - timedelta(days=args.window_days)).timestamp()
        if args.window_days > 0 else None
    )
    source = args.source or None

    if args.accept_seed:
        return _write_seed_artifact(args.reason)

    print("=" * 60)
    print("探针阈值重校准报告 (ISSUE-002)")
    if since_ts is not None or source:
        print(f"样本过滤: window_days={args.window_days or 'all'} source={source or 'all'}")
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

    # L4: 小样本守卫 — 不足则保持现有阈值，避免退化阈值
    if total < MIN_SAMPLES:
        print(f"⚠️ 样本不足 ({total} < {MIN_SAMPLES})，跳过校准以保持现有阈值")
        print("  原因: 小样本分位数退化 (P75≈P95) 产出无效阈值 (见 L4)")
        return

    results = {}
    for probe in ["oscillation", "entropy"]:
        print(f"\n{'─' * 40}")
        r = analyze_probe(probe, since_ts=since_ts, source=source)
        if r["total_readings"] < MIN_SAMPLES:
            print(f"⚠️ {probe} 过滤后样本不足 ({r['total_readings']} < {MIN_SAMPLES})，跳过该校准")
            return
        results[probe] = r

        print(f"\n{probe} 探针:")
        print(f"  总读数: {r['total_readings']}")
        print(f"  值范围: {r['value_range']}")

        print("\n  分位数:")
        for k, v in r["percentiles"].items():
            print(f"    {k}: {v}")

        print("\n  新阈值方案:")
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

    degenerate = {k: v["degenerate_reason"] for k, v in results.items() if v["degenerate_reason"]}
    if degenerate:
        print("\n" + "=" * 60)
        print("⚠️ 拒绝写入：分位阈值退化，现有阈值保持不变")
        for name, why in degenerate.items():
            print(f"  - {name}: {why}")
        print("  退化分布下写出的阈值会让该探针失去分辨力（正常区间为单点或全等值）。")
        print("  请等清洗后的样本积累；如需先让 --verify 通过，可用 --accept-seed 显式标记未校准。")
        return 0

    generated_at = datetime.now(timezone.utc).isoformat()
    per_probe = {
        k: {
            "total_readings": v["total_readings"],
            "value_range": v["value_range"],
            "percentiles": v["percentiles"],
        }
        for k, v in results.items()
    }
    filters = {"window_days": args.window_days, "source": source}
    config = {
        "calibrated_at": generated_at,
        "method": "percentile_based",
        "min_samples": MIN_SAMPLES,
        "filters": filters,
        "samples": {k: v["total_readings"] for k, v in results.items()},
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

    artifact = {
        "generated_at": generated_at,
        "provenance": "percentile_based",
        "config_path": str(CONFIG_PATH),
        "config_sha256": _sha256_of(CONFIG_PATH),
        "config": config,
        "db": _db_fingerprint(),
        "filters": filters,
        "per_probe": per_probe,
        "script": os.path.basename(__file__),
    }
    os.makedirs(os.path.dirname(ARTIFACT_PATH), exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print(f"\n阈值配置已保存: {CONFIG_PATH}")
    print(f"校准产物已保存: {ARTIFACT_PATH}")

    estimated_confidence = compute_estimated_confidence(results)
    print(f"\n{'=' * 60}")
    print(f"预估重校准后置信度: {estimated_confidence}")
    print("重校准前置信度: 12.0")
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
    _args = _parse_args(sys.argv[1:])
    if _args.verify:
        sys.exit(verify())
    main(sys.argv[1:])
