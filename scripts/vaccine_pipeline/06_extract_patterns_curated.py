#!/usr/bin/env python3
"""
阶段6: 从 curated/analytics 层提取攻击模式 (v3 — 多数据源融合)

输入源 (优先级):
1. curated/violation_patterns - 已聚类的违规模式
2. analytics/rule_effectiveness - 高 FP/高漂移规则
3. analytics/agent_health_index - 低健康 Agent 的行为异常
4. curated/cross_agent_flows - 多 Agent 协作异常链路
5. curated/tool_executions - 工具执行异常 (高延迟、高拦截、错误模式)
6. raw/audit_logs - 传统审计日志 (兼容)

输出: vaccines/patterns_curated.json (增强模式集)
"""

import json
import os
import sys
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

from maref_config import vaccine_path

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))

OWASP_PATTERNS = [
    {"class": "ASI01_prompt_injection", "trigger": "untrusted_input_in_system_prompt"},
    {"class": "ASI02_output_handling", "trigger": "sensitive_output_not_sanitized"},
    {"class": "ASI03_supply_chain", "trigger": "unverified_plugin_loaded"},
    {"class": "ASI04_data_poisoning", "trigger": "untrusted_fine_tuning_data"},
    {"class": "ASI05_improper_error_handling", "trigger": "error_context_leaked"},
    {"class": "ASI06_excessive_agency", "trigger": "unscoped_tool_permission"},
    {"class": "ASI07_system_prompt_leakage", "trigger": "internal_prompt_exposed"},
    {"class": "ASI08_vector_weakness", "trigger": "embedding_manipulation"},
    {"class": "ASI09_misinformation", "trigger": "hallucinated_governance_output"},
    {"class": "ASI10_unbounded_consumption", "trigger": "token_loop_detected"},
]


def make_id(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def _load_curated_violation_patterns(days: int = 30) -> list[dict]:
    """加载 curated/violation_patterns"""
    patterns = []
    if not DUCKDB_AVAILABLE:
        return patterns

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/violation_patterns/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            patterns.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 violation_patterns 失败: {e}")
    return patterns


def _load_rule_effectiveness(days: int = 30) -> list[dict]:
    """加载 analytics/rule_effectiveness"""
    patterns = []
    if not DUCKDB_AVAILABLE:
        return patterns

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/rule_effectiveness/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            patterns.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 rule_effectiveness 失败: {e}")
    return patterns


def _load_agent_health(days: int = 30) -> list[dict]:
    """加载 analytics/agent_health_index"""
    patterns = []
    if not DUCKDB_AVAILABLE:
        return patterns

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/agent_health_index/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            patterns.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 agent_health_index 失败: {e}")
    return patterns


def _load_cross_agent_flows(days: int = 30) -> list[dict]:
    """加载 curated/cross_agent_flows"""
    patterns = []
    if not DUCKDB_AVAILABLE:
        return patterns

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/cross_agent_flows/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            patterns.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 cross_agent_flows 失败: {e}")
    return patterns


def _load_tool_executions(days: int = 7) -> list[dict]:
    """加载 curated/tool_executions (最近 7 天)"""
    patterns = []
    if not DUCKDB_AVAILABLE:
        return patterns

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/tool_executions/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            patterns.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 tool_executions 失败: {e}")
    return patterns


def extract_from_violation_patterns(patterns: list[dict]) -> list[dict]:
    """从 violation_patterns 提取模式"""
    extracted = []
    for p in patterns:
        if p.get("occurrence_count", 0) < 3:
            continue
        extracted.append({
            "pattern_id": p.get("pattern_id", make_id(p.get("signature", ""))),
            "attack_class": p.get("pattern_type", "violation_pattern"),
            "attack_subtype": p.get("signature", "unknown")[:50],
            "trigger": f"violation_{p.get('pattern_type', 'unknown')}",
            "count": p.get("occurrence_count", 0),
            "dimension": "curated_violation",
            "evidence": {
                "first_seen": p.get("first_seen"),
                "last_seen": p.get("last_seen"),
                "affected_agents": p.get("affected_agents"),
                "affected_tools": p.get("affected_tools"),
                "evolution_stage": p.get("evolution_stage"),
            },
        })
    return extracted


def extract_from_rule_effectiveness(patterns: list[dict]) -> list[dict]:
    """从规则有效度提取高风险规则模式"""
    extracted = []
    for p in patterns:
        fp = p.get("false_positive_est", 0)
        drift = p.get("drift_score", 0)
        coverage = p.get("coverage_rate", 0)
        tier = p.get("effectiveness_tier", "")

        # 高误报、高漂移、低覆盖 = 高风险
        risk_score = fp * 0.5 + drift * 0.3 + (1 - coverage) * 0.2
        if risk_score < 0.3 and tier != "low":
            continue

        extracted.append({
            "pattern_id": make_id(f"rule_risk_{p.get('rule_id', '')}"),
            "attack_class": "rule_degradation",
            "attack_subtype": p.get("rule_id", "unknown"),
            "trigger": f"rule_fp_{fp:.2f}_drift_{drift:.2f}",
            "count": p.get("total_evaluations", 0),
            "dimension": "rule_effectiveness",
            "risk_score": round(risk_score, 3),
            "evidence": {
                "false_positive_est": fp,
                "drift_score": drift,
                "coverage_rate": coverage,
                "effectiveness_tier": tier,
                "recommendation": p.get("recommendation", ""),
            },
        })
    return extracted


def extract_from_agent_health(patterns: list[dict]) -> list[dict]:
    """从 Agent 健康指数提取异常行为模式"""
    extracted = []
    for p in patterns:
        health = p.get("composite_health", 100)
        violation_rate = p.get("violation_rate", 0)
        interception_rate = p.get("interception_rate", 0)
        tier = p.get("health_tier", "excellent")

        if tier in ("excellent", "good") and health > 70:
            continue

        extracted.append({
            "pattern_id": make_id(f"agent_unhealthy_{p.get('agent_id', '')}"),
            "attack_class": "agent_health_anomaly",
            "attack_subtype": p.get("agent_id", "unknown"),
            "trigger": f"health_{tier}_violation_{violation_rate:.2f}",
            "count": 1,
            "dimension": "agent_health",
            "health_score": health,
            "evidence": {
                "health_tier": tier,
                "violation_rate": violation_rate,
                "interception_rate": interception_rate,
                "trust_score": p.get("trust_score"),
                "alerts": p.get("alerts"),
            },
        })
    return extracted


def extract_from_cross_agent_flows(patterns: list[dict]) -> list[dict]:
    """从跨 Agent 协作流提取异常链路模式"""
    extracted = []
    for p in patterns:
        outcome = p.get("final_outcome", "")
        interceptions = p.get("total_interceptions", 0)
        hitl = p.get("total_hitl", 0)
        total_tools = p.get("total_tool_calls", 0)

        if outcome == "success" and interceptions == 0:
            continue

        try:
            agent_seq = json.loads(p.get("agent_sequence", "[]"))
        except Exception:
            agent_seq = []

        extracted.append({
            "pattern_id": make_id(f"flow_anomaly_{p.get('correlation_id', '')}"),
            "attack_class": "cross_agent_anomaly",
            "attack_subtype": f"{len(agent_seq)}_agent_flow",
            "trigger": f"flow_{outcome}_intercept_{interceptions}",
            "count": 1,
            "dimension": "cross_agent_flow",
            "evidence": {
                "correlation_id": p.get("correlation_id"),
                "chain_id": p.get("chain_id"),
                "agent_sequence": agent_seq,
                "total_tool_calls": total_tools,
                "interceptions": interceptions,
                "hitl": hitl,
                "duration_ms": p.get("total_duration_ms"),
                "bottleneck_agent": p.get("bottleneck_agent"),
                "bottleneck_tool": p.get("bottleneck_tool"),
            },
        })
    return extracted


def extract_from_tool_executions(patterns: list[dict]) -> list[dict]:
    """从工具执行记录提取异常模式"""
    extracted = []

    # 按工具聚合
    by_tool = defaultdict(list)
    for p in patterns:
        by_tool[p.get("tool_name", "unknown")].append(p)

    for tool_name, executions in by_tool.items():
        if len(executions) < 10:
            continue

        total = len(executions)
        denied = sum(1 for e in executions if e.get("verdict") == "deny")
        intercepted = sum(1 for e in executions if e.get("verdict") == "ask_user")
        errors = sum(1 for e in executions if e.get("error"))
        avg_latency = sum(e.get("latency_ms", 0) for e in executions) / total

        deny_rate = denied / total
        intercept_rate = intercepted / total
        error_rate = errors / total

        # 高拦截率、高错误率、高延迟 = 异常
        if deny_rate < 0.1 and intercept_rate < 0.1 and error_rate < 0.05 and avg_latency < 1000:
            continue

        extracted.append({
            "pattern_id": make_id(f"tool_anomaly_{tool_name}"),
            "attack_class": "tool_execution_anomaly",
            "attack_subtype": tool_name,
            "trigger": f"tool_deny_{deny_rate:.2f}_intercept_{intercept_rate:.2f}_error_{error_rate:.2f}_lat_{avg_latency:.0f}",
            "count": total,
            "dimension": "tool_execution",
            "evidence": {
                "deny_rate": round(deny_rate, 3),
                "intercept_rate": round(intercept_rate, 3),
                "error_rate": round(error_rate, 3),
                "avg_latency_ms": round(avg_latency, 1),
                "total_executions": total,
            },
        })
    return extracted


def extract_owasp_theoretical() -> list[dict]:
    """OWASP 理论模式"""
    patterns = []
    for p in OWASP_PATTERNS:
        p_copy = p.copy()
        p_copy["pattern_id"] = make_id(p["trigger"])
        p_copy["attack_class"] = p["class"]
        p_copy["attack_subtype"] = "theoretical"
        p_copy["count"] = 0
        p_copy["dimension"] = "owasp_theoretical"
        patterns.append(p_copy)
    return patterns


def main():
    parser = argparse.ArgumentParser(description="从 curated/analytics 层提取攻击模式 v3")
    parser.add_argument("--days", type=int, default=30, help="回溯天数")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    print("=" * 60)
    print("攻击模式抽取 v3 (curated/analytics 多数据源融合)")
    print("=" * 60)

    if not DUCKDB_AVAILABLE:
        print("⚠️  duckdb 未安装，仅输出 OWASP 理论模式")
        print("   安装: pip install duckdb")
        all_patterns = extract_owasp_theoretical()
        print(f"\n总提取模式: {len(all_patterns)} (仅理论)")

        if not args.dry_run:
            output_path = str(vaccine_path("patterns_curated.json"))
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(all_patterns, f, indent=2, ensure_ascii=False)
            print(f"模式已保存: {output_path}")
        return

    all_patterns = []

    # 1. Curated 违规模式
    print(f"\n--- 维度1: curated/violation_patterns (回溯 {args.days} 天) ---")
    vp = _load_curated_violation_patterns(args.days)
    evp = extract_from_violation_patterns(vp)
    print(f"提取模式: {len(evp)}")
    for p in evp[:5]:
        print(f"  {p['attack_class']}::{p['attack_subtype']} ({p['count']}x)")
    all_patterns.extend(evp)

    # 2. 规则有效度风险
    print(f"\n--- 维度2: analytics/rule_effectiveness ---")
    re = _load_rule_effectiveness(args.days)
    ere = extract_from_rule_effectiveness(re)
    print(f"提取高风险规则: {len(ere)}")
    for p in ere[:5]:
        print(f"  {p['attack_class']}::{p['attack_subtype']} (risk={p.get('risk_score',0)})")
    all_patterns.extend(ere)

    # 3. Agent 健康异常
    print(f"\n--- 维度3: analytics/agent_health_index ---")
    ah = _load_agent_health(args.days)
    eah = extract_from_agent_health(ah)
    print(f"提取异常 Agent: {len(eah)}")
    for p in eah[:5]:
        print(f"  {p['attack_class']}::{p['attack_subtype']} (health={p.get('health_score',0):.1f})")
    all_patterns.extend(eah)

    # 4. 跨 Agent 协作异常
    print(f"\n--- 维度4: curated/cross_agent_flows ---")
    caf = _load_cross_agent_flows(args.days)
    ecaf = extract_from_cross_agent_flows(caf)
    print(f"提取异常协作流: {len(ecaf)}")
    for p in ecaf[:5]:
        print(f"  {p['attack_class']}::{p['attack_subtype']} ({p['evidence'].get('interceptions',0)} 拦截)")
    all_patterns.extend(ecaf)

    # 5. 工具执行异常
    print(f"\n--- 维度5: curated/tool_executions (回溯 7 天) ---")
    te = _load_tool_executions(7)
    ete = extract_from_tool_executions(te)
    print(f"提取异常工具: {len(ete)}")
    for p in ete[:5]:
        print(f"  {p['attack_class']}::{p['attack_subtype']} (deny={p['evidence'].get('deny_rate',0):.1%})")
    all_patterns.extend(ete)

    # 6. OWASP 理论模式
    print(f"\n--- 维度6: OWASP 理论模式 ---")
    owasp = extract_owasp_theoretical()
    print(f"注入理论模式: {len(owasp)}")
    all_patterns.extend(owasp)

    print(f"\n{'=' * 60}")
    print(f"总提取模式: {len(all_patterns)}")
    print(f"目标: ≥50 (v3 增强)")
    print(f"状态: {'✅ 达标' if len(all_patterns) >= 50 else '⚠️ 未达标'}")

    if not args.dry_run:
        output_path = str(vaccine_path("patterns_curated.json"))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(all_patterns, f, indent=2, ensure_ascii=False)
        print(f"\n模式已保存: {output_path}")

    return 0


if __name__ == "__main__":
    import argparse
    sys.exit(main())