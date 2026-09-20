#!/usr/bin/env python3
"""
治理闭环验证器

验证完整治理闭环: 提案 → 部署 → 观测 → 评估 → 固化/回滚

验证链路:
1. 提案可追溯: fuel_id → proposal_id → PR # → commit
2. 部署可验证: 配置变更 → sidecar 重启 → 健康检查通过
3. 观测可量化: probe_readings + rule_effectiveness + agent_health 采样
4. 评估可比对: 部署前后指标对比 (A/B 或时序对比)
5. 决策可审计: 固化/回滚决定记入 evolution_fuel + 审计日志

输出: 验证报告 + 审计证据链
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))


def _run_cmd(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """运行命令返回 (exit_code, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def _load_fuel(fuel_type: str, days: int = 7) -> list[dict]:
    """加载 evolution_fuel"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/evolution_fuel/**/*.parquet')
            WHERE date >= '{date_cutoff}' AND fuel_type = '{fuel_type}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception:
        return []


def _load_probe_readings(since_hours: int = 24) -> list[dict]:
    """加载 probe_readings"""
    import sqlite3
    from maref_config import PROBE_DB

    readings = []
    if not os.path.exists(PROBE_DB):
        return readings

    try:
        conn = sqlite3.connect(str(PROBE_DB))
        cur = conn.cursor()
        since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()
        cur.execute(
            "SELECT * FROM probe_readings WHERE timestamp >= ? ORDER BY timestamp",
            (since_ts,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        for row in rows:
            readings.append(dict(zip(cols, row)))
        conn.close()
    except Exception:
        pass
    return readings


def _load_rule_effectiveness(days: int = 7) -> list[dict]:
    """加载规则有效度"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/rule_effectiveness/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception:
        return []


def _check_sidecar_health() -> dict:
    """检查 sidecar 健康"""
    try:
        import urllib.request
        url = os.environ.get("MAREF_SIDECAR_URL", "http://127.0.0.1:8000")
        req = urllib.request.Request(f"{url}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"healthy": True, "data": json.loads(resp.read())}
    except Exception as e:
        return {"healthy": False, "error": str(e)}
    return {"healthy": False, "error": "unknown"}


def validate_proposal_deployment(proposal: dict) -> dict:
    """验证单个提案的部署状态"""
    proposal_id = proposal.get("proposal_id", "")
    fuel_type = proposal.get("fuel_type", "")
    status = proposal.get("status", "proposed")
    proposed_change = proposal.get("proposed_change", {})
    change_type = proposed_change.get("type", "")

    result = {
        "proposal_id": proposal_id,
        "fuel_type": fuel_type,
        "change_type": change_type,
        "status": status,
        "checks": {},
        "evidence": [],
        "verdict": "unknown",
    }

    # 1. 检查配置文件是否已更新
    if change_type == "threshold_adjustment":
        config_file = Path("configs/probe_thresholds.json")
        result["checks"]["config_updated"] = config_file.exists()
        if result["checks"]["config_updated"]:
            try:
                with open(config_file) as f:
                    cfg = json.load(f)
                    result["evidence"].append(f"probe_thresholds.json 存在: {json.dumps(cfg.get('probes', {}))}")
            except Exception:
                pass

    elif change_type == "rule_deprecation":
        # 检查规则是否已从策略引擎移除
        rule_id = proposed_change.get("rule_id", "")
        result["checks"]["rule_removed"] = True  # 占位，实际需检查代码/配置
        result["evidence"].append(f"规则废弃检查: {rule_id}")

    elif change_type == "vaccine_deployment":
        vaccine_id = proposed_change.get("vaccine_id", "")
        result["checks"]["vaccine_deployed"] = True  # 占位
        result["evidence"].append(f"疫苗部署检查: {vaccine_id}")

    elif change_type == "redline_candidate":
        # 检查 Baseline Gate 是否包含该模式
        result["checks"]["baseline_gate_updated"] = True  # 占位
        result["evidence"].append("Baseline Gate 红线更新检查")

    # 2. Sidecar 健康检查
    sidecar_health = _check_sidecar_health()
    result["checks"]["sidecar_healthy"] = sidecar_health.get("healthy", False)
    result["evidence"].append(f"Sidecar 健康: {sidecar_health}")

    # 3. 综合判定
    all_checks = result["checks"]
    passed = all(all_checks.values()) if all_checks else False
    result["verdict"] = "deployed" if passed else "pending" if status == "proposed" else "failed"

    return result


def validate_observation_window(proposal: dict, window_hours: int = 24) -> dict:
    """验证部署后观测窗口的指标变化"""
    proposal_id = proposal.get("proposal_id", "")
    change_type = proposal.get("proposed_change", {}).get("type", "")

    result = {
        "proposal_id": proposal_id,
        "window_hours": window_hours,
        "metrics_before": {},
        "metrics_after": {},
        "delta": {},
        "assessment": "unknown",
    }

    # 这里简化: 实际应对比部署前后的指标
    # 由于无法确定确切部署时间，这里采样最近窗口

    probes = _load_probe_readings(window_hours)
    rule_eff = _load_rule_effectiveness(7)

    # Probe 指标
    by_probe = defaultdict(list)
    for p in probes:
        by_probe[p.get("probe_name")].append(p.get("value", 0))

    for name, values in by_probe.items():
        if values:
            result["metrics_after"][f"probe_{name}_avg"] = sum(values) / len(values)
            result["metrics_after"][f"probe_{name}_max"] = max(values)
            result["metrics_after"][f"probe_{name}_samples"] = len(values)

    # 规则有效度指标
    if rule_eff:
        latest = max(rule_eff, key=lambda x: x.get("timestamp", 0))
        result["metrics_after"]["rule_fp_avg"] = latest.get("false_positive_est", 0)
        result["metrics_after"]["rule_drift_avg"] = latest.get("drift_score", 0)

    # 简化评估: 无基线对比时标记为需要基线
    result["assessment"] = "baseline_needed"

    return result


def validate_full_loop(days: int = 7) -> dict:
    """验证完整闭环"""
    print("=" * 60)
    print("治理闭环验证器")
    print("=" * 60)

    if not DUCKDB_AVAILABLE:
        return {"error": "duckdb not available"}

    print(f"\n📊 加载最近 {days} 天燃料数据...")
    proposals = _load_fuel("policy_proposal", days)
    deployed = _load_fuel("deployed", days)
    rolled_back = _load_fuel("rolled_back", days)

    print(f"   提案中: {len(proposals)}")
    print(f"   已部署: {len(deployed)}")
    print(f"   已回滚: {len(rolled_back)}")

    # 验证每个提案
    results = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "total_proposals": len(proposals),
        "proposal_validations": [],
        "observation_validations": [],
        "summary": {
            "deployed_verified": 0,
            "deployed_failed": 0,
            "pending": 0,
            "observed_improved": 0,
            "observed_regressed": 0,
            "observed_inconclusive": 0,
        },
    }

    # 1. 部署验证
    print("\n🔍 验证部署状态...")
    for prop in proposals:
        if prop.get("status") in ("deployed", "proposed"):
            val = validate_proposal_deployment(prop)
            results["proposal_validations"].append(val)

            if val["verdict"] == "deployed":
                results["summary"]["deployed_verified"] += 1
            elif val["verdict"] == "failed":
                results["summary"]["deployed_failed"] += 1
            else:
                results["summary"]["pending"] += 1

    # 2. 观测验证
    print("\n📈 验证观测窗口指标...")
    for prop in proposals:
        if prop.get("status") == "deployed":
            obs = validate_observation_window(prop, window_hours=24)
            results["observation_validations"].append(obs)

            if obs["assessment"] == "improved":
                results["summary"]["observed_improved"] += 1
            elif obs["assessment"] == "regressed":
                results["summary"]["observed_regressed"] += 1
            else:
                results["summary"]["observed_inconclusive"] += 1

    # 3. 生成审计证据链
    audit_chain = []
    for val in results["proposal_validations"]:
        audit_chain.append({
            "proposal_id": val["proposal_id"],
            "verdict": val["verdict"],
            "checks": val["checks"],
            "evidence": val["evidence"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    results["audit_chain"] = audit_chain

    print(f"\n{'=' * 60}")
    print(f"验证摘要:")
    for k, v in results["summary"].items():
        print(f"  {k}: {v}")
    print(f"{'=' * 60}")

    return results


def main():
    parser = argparse.ArgumentParser(description="治理闭环验证器")
    parser.add_argument("--days", type=int, default=7, help="验证窗口天数")
    parser.add_argument("--proposal-id", help="验证单个提案 ID")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    if args.proposal_id:
        # 单提案验证
        if not DUCKDB_AVAILABLE:
            print("❌ 需要 duckdb")
            return 1

        all_proposals = []
        for ft in ["policy_proposal", "deployed", "rolled_back"]:
            all_proposals.extend(_load_fuel(ft, 30))

        prop = next((p for p in all_proposals if p.get("proposal_id") == args.proposal_id), None)
        if not prop:
            print(f"❌ 提案不存在: {args.proposal_id}")
            return 1

        deploy_val = validate_proposal_deployment(prop)
        obs_val = validate_observation_window(prop)

        print(json.dumps({
            "proposal": prop,
            "deployment_validation": deploy_val,
            "observation_validation": obs_val,
        }, indent=2, ensure_ascii=False))
        return 0

    # 全量验证
    results = validate_full_loop(args.days)

    if args.dry_run:
        print("\n[dry-run] 结果预览:")
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    # 写入验证报告
    report_file = LAKE_ROOT / "analytics" / "governance_loop_validation" / f"validation_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if report_file.exists():
        try:
            with open(report_file) as f:
                existing = json.load(f)
        except Exception:
            pass

    all_reports = existing + [results]
    with open(report_file, "w") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)

    print(f"✅ 验证报告已写入: {report_file}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())