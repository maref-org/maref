#!/usr/bin/env python3
"""
红线模式自动发现

从 curated/analytics 层挖掘新型治理绕过/红线违规模式，自动提交 Baseline Gate 红线候选

检测维度:
1. 序列模式挖掘: 绕过治理的行为序列 (频繁项集、序列模式)
2. 聚类分析: 异常行为聚类 (DBSCAN/KMeans on 嵌入向量)
3. 关联规则: 条件 → 红线违规 的强关联
4. 异常检测: Isolation Forest 识别新型攻击向量

输出: evolution_fuel 中 redline_candidate 类型燃料
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import DBSCAN
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from maref_config import config_path

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))

# Baseline Gate 现有红线模式 (用于对比去重)
EXISTING_REDLINE_PATTERNS = {
    "删除审计日志", "压缩审计日志", "跳过审计", "清理审计", "清空审计",
    "删除 governance_audit", "不再记录", "不写审计",
    "明文保存", "明文存储", "cookie 明文", "明文密码", "输出 token", "输出密钥",
    "降低阈值", "下调阈值", "下调", "调低", "移除兜底", "移除上限", "绕过门禁",
    "放行 ai 味", "跳过质量", "放开阈值", "放宽阈值",
    "熔断不记录", "失败计数清零", "静默熔断", "熔断日志不写",
    "试点运行", "小范围测试", "折中方案", "先试点", "暂不删除", "暂时跳过",
}


def _load_governance_decisions(days: int = 30) -> list[dict]:
    """加载 curated/governance_decisions"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/governance_decisions/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception as e:
        print(f"⚠️  加载 governance_decisions 失败: {e}")
        return []


def _load_tool_executions(days: int = 30) -> list[dict]:
    """加载 curated/tool_executions"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/tool_executions/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception as e:
        print(f"⚠️  加载 tool_executions 失败: {e}")
        return []


def _load_violation_patterns(days: int = 30) -> list[dict]:
    """加载 curated/violation_patterns"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/violation_patterns/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception as e:
        print(f"⚠️  加载 violation_patterns 失败: {e}")
        return []


def _load_cross_agent_flows(days: int = 30) -> list[dict]:
    """加载 curated/cross_agent_flows"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/curated/cross_agent_flows/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception as e:
        print(f"⚠️  加载 cross_agent_flows 失败: {e}")
        return []


def _build_behavior_sequences(decisions: list[dict], executions: list[dict]) -> dict[str, list[dict]]:
    """按 correlation_id 构建行为序列"""
    by_corr = defaultdict(list)

    for d in decisions:
        corr = d.get("correlation_id")
        if corr:
            by_corr[corr].append({
                "type": "decision",
                "timestamp": d.get("timestamp"),
                "agent": d.get("agent_id"),
                "tool": d.get("tool_name"),
                "verdict": d.get("verdict"),
                "rule": d.get("matched_rule"),
                "reason": d.get("reason"),
            })

    for e in executions:
        corr = e.get("correlation_id")
        if corr:
            by_corr[corr].append({
                "type": "execution",
                "timestamp": e.get("timestamp"),
                "agent": e.get("agent_id"),
                "tool": e.get("tool_name"),
                "verdict": e.get("verdict"),
                "latency": e.get("latency_ms"),
                "error": e.get("error"),
            })

    # 排序
    for corr in by_corr:
        by_corr[corr].sort(key=lambda x: x.get("timestamp", 0))

    return by_corr


def _extract_sequence_patterns(sequences: dict[str, list[dict]], min_support: int = 3) -> list[dict]:
    """提取频繁行为序列模式 (简化版 PrefixSpan)"""
    patterns = []

    # 将序列转为字符串表示
    seq_strings = []
    for corr, events in sequences.items():
        if len(events) < 2:
            continue
        seq_str = " -> ".join(
            f"{e['type']}:{e.get('verdict','')}/{e.get('tool','')}"
            for e in events
        )
        seq_strings.append((corr, seq_str, events))

    # 统计 n-gram (n=2,3,4)
    ngram_counts = Counter()
    for corr, seq_str, events in seq_strings:
        parts = seq_str.split(" -> ")
        for n in [2, 3, 4]:
            for i in range(len(parts) - n + 1):
                ngram = " -> ".join(parts[i:i+n])
                ngram_counts[ngram] += 1

    for ngram, count in ngram_counts.items():
        if count >= min_support:
            # 检查是否包含可疑模式
            suspicious = any(
                kw in ngram.lower()
                for kw in ["deny", "ask_user", "intercept", "hitl", "bypass", "circuit_breaker"]
            )
            if suspicious:
                patterns.append({
                    "pattern_type": "frequent_sequence",
                    "sequence": ngram,
                    "support": count,
                    "suspicious": True,
                })

    return patterns


def _cluster_anomalous_behaviors(decisions: list[dict], executions: list[dict]) -> list[dict]:
    """聚类异常行为 (使用 TF-IDF + DBSCAN)"""
    if not SKLEARN_AVAILABLE or not decisions:
        return []

    # 构建文档: 每个 correlation_id 的行为描述
    by_corr = defaultdict(list)
    for d in decisions:
        corr = d.get("correlation_id")
        if corr:
            by_corr[corr].append(f"{d.get('verdict','')}:{d.get('tool_name','')}:{d.get('matched_rule','')}")

    docs = []
    corr_ids = []
    for corr, events in by_corr.items():
        if len(events) >= 2:  # 至少 2 个决策
            docs.append(" ".join(events))
            corr_ids.append(corr)

    if len(docs) < 10:
        return []

    # TF-IDF 向量化
    vectorizer = TfidfVectorizer(max_features=100, stop_words=None)
    try:
        X = vectorizer.fit_transform(docs)
    except Exception:
        return []

    # DBSCAN 聚类
    clustering = DBSCAN(eps=0.5, min_samples=3, metric='cosine')
    labels = clustering.fit_predict(X.toarray())

    clusters = []
    for label in set(labels):
        if label == -1:
            continue  # 噪声点
        indices = [i for i, l in enumerate(labels) if l == label]
        if len(indices) >= 3:
            cluster_docs = [docs[i] for i in indices]
            # 提取共同特征
            common_terms = set(cluster_docs[0].split())
            for d in cluster_docs[1:]:
                common_terms &= set(d.split())

            clusters.append({
                "pattern_type": "behavior_cluster",
                "cluster_id": int(label),
                "size": len(indices),
                "common_features": list(common_terms)[:10],
                "correlation_ids": [corr_ids[i] for i in indices],
            })

    return clusters


def _detect_association_rules(decisions: list[dict]) -> list[dict]:
    """挖掘关联规则: 条件 → 红线违规"""
    if not decisions:
        return []

    # 收集所有 (rule, verdict) 对
    rule_verdicts = defaultdict(Counter)
    for d in decisions:
        rule = d.get("matched_rule", "")
        verdict = d.get("verdict", "")
        if rule and verdict:
            rule_verdicts[rule][verdict] += 1

    rules = []
    for rule, verdicts in rule_verdicts.items():
        total = sum(verdicts.values())
        deny_rate = verdicts.get("deny", 0) / total
        ask_rate = verdicts.get("ask_user", 0) / total

        # 高拒绝/拦截率的规则
        if (deny_rate + ask_rate) > 0.5 and total >= 10:
            rules.append({
                "pattern_type": "high_intercept_rule",
                "rule": rule,
                "deny_rate": round(deny_rate, 3),
                "ask_user_rate": round(ask_rate, 3),
                "total_cases": total,
                "confidence": round(deny_rate + ask_rate, 3),
            })

    return rules


def _isolation_forest_anomalies(executions: list[dict]) -> list[dict]:
    """Isolation Forest 检测工具执行异常"""
    if not SKLEARN_AVAILABLE or len(executions) < 50:
        return []

    # 特征工程
    features = []
    meta = []
    for e in executions:
        try:
            lat = e.get("latency_ms", 0)
            verdict_map = {"allow": 0, "deny": 1, "ask_user": 2}
            verd = verdict_map.get(e.get("verdict", ""), 3)
            error = 1 if e.get("error") else 0
            tokens = e.get("tokens_input", 0) + e.get("tokens_output", 0)
            cost = e.get("cost_usd", 0) * 10000  # 放大

            features.append([lat, verd, error, tokens, cost])
            meta.append({
                "correlation_id": e.get("correlation_id"),
                "agent": e.get("agent_id"),
                "tool": e.get("tool_name"),
                "latency": lat,
                "verdict": e.get("verdict"),
            })
        except Exception:
            continue

    if len(features) < 50:
        return []

    X = np.array(features)
    # 标准化
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Isolation Forest
    clf = IsolationForest(contamination=0.05, random_state=42)
    preds = clf.fit_predict(X_scaled)
    scores = clf.score_samples(X_scaled)

    anomalies = []
    for i, (pred, score) in enumerate(zip(preds, scores)):
        if pred == -1:  # 异常
            anomalies.append({
                "pattern_type": "isolation_forest_anomaly",
                "anomaly_score": round(float(score), 4),
                "details": meta[i],
            })

    return anomalies


def _check_existing_redline(signature: str) -> bool:
    """检查是否已在 Baseline Gate 红线中"""
    signature_lower = signature.lower()
    for existing in EXISTING_REDLINE_PATTERNS:
        if existing in signature_lower or signature_lower in existing:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="红线模式自动发现")
    parser.add_argument("--days", type=int, default=30, help="回溯天数")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    print("=" * 60)
    print("红线模式自动发现")
    print("=" * 60)

    if not DUCKDB_AVAILABLE:
        print("❌ 需要 duckdb")
        return 1

    print(f"\n📊 加载最近 {args.days} 天数据...")
    decisions = _load_governance_decisions(args.days)
    executions = _load_tool_executions(args.days)
    violations = _load_violation_patterns(args.days)
    flows = _load_cross_agent_flows(args.days)

    print(f"   治理决策: {len(decisions)}")
    print(f"   工具执行: {len(executions)}")
    print(f"   违规模式: {len(violations)}")
    print(f"   协作流: {len(flows)}")

    all_candidates = []

    # 1. 序列模式挖掘
    print("\n🔍 序列模式挖掘...")
    sequences = _build_behavior_sequences(decisions, executions)
    print(f"   行为序列: {len(sequences)}")
    seq_patterns = _extract_sequence_patterns(sequences)
    print(f"   频繁可疑序列: {len(seq_patterns)}")
    for p in seq_patterns:
        signature = f"序列:{p['sequence']}"
        if not _check_existing_redline(signature):
            all_candidates.append({
                "fuel_type": "redline_candidate",
                "source": "sequence_mining",
                "priority": 1,
                "title": f"频繁绕过序列: {p['sequence'][:80]}",
                "description": f"检测到频繁出现的可疑行为序列 (support={p['support']})",
                "evidence": {"sequence": p["sequence"], "support": p["support"]},
                "proposed_change": {"add_to_baseline_gate": {"pattern": signature, "severity": 0.85}},
                "impact_estimate": {"false_positive_risk": "medium", "coverage_gain": "high"},
                "status": "proposed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    # 2. 行为聚类
    print("\n🔍 行为聚类分析...")
    if SKLEARN_AVAILABLE:
        clusters = _cluster_anomalous_behaviors(decisions, executions)
        print(f"   异常聚类: {len(clusters)}")
        for c in clusters:
            signature = f"聚类:{c['common_features'][:5]}"
            if not _check_existing_redline(signature):
                all_candidates.append({
                    "fuel_type": "redline_candidate",
                    "source": "behavior_clustering",
                    "priority": 1,
                    "title": f"异常行为聚类 #{c['cluster_id']} (size={c['size']})",
                    "description": f"DBSCAN 发现异常行为聚类，共同特征: {c['common_features'][:5]}",
                    "evidence": {"cluster": c},
                    "proposed_change": {"add_to_baseline_gate": {"pattern": signature, "severity": 0.8}},
                    "impact_estimate": {"false_positive_risk": "low", "coverage_gain": "medium"},
                    "status": "proposed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    else:
        print("   ⚠️  sklearn 未安装，跳过聚类")

    # 3. 关联规则
    print("\n🔍 关联规则挖掘...")
    assoc_rules = _detect_association_rules(decisions)
    print(f"   高拦截规则: {len(assoc_rules)}")
    for r in assoc_rules:
        signature = f"规则:{r['rule']}"
        if not _check_existing_redline(signature):
            all_candidates.append({
                "fuel_type": "redline_candidate",
                "source": "association_rules",
                "priority": 2,
                "title": f"高拦截规则关联: {r['rule']}",
                "description": f"规则 {r['rule']} 导致 {r['deny_rate']:.0%} 拒绝 + {r['ask_user_rate']:.0%} HITL",
                "evidence": r,
                "proposed_change": {"add_to_baseline_gate": {"pattern": signature, "severity": 0.75}},
                "impact_estimate": {"false_positive_risk": "medium", "coverage_gain": "high"},
                "status": "proposed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    # 4. Isolation Forest 异常
    print("\n🔍 Isolation Forest 异常检测...")
    if SKLEARN_AVAILABLE:
        anomalies = _isolation_forest_anomalies(executions)
        print(f"   执行异常: {len(anomalies)}")
        for a in anomalies[:10]:
            signature = f"异常:{a['details']['tool']}:{a['details']['verdict']}"
            if not _check_existing_redline(signature):
                all_candidates.append({
                    "fuel_type": "redline_candidate",
                    "source": "isolation_forest",
                    "priority": 2,
                    "title": f"工具执行异常: {a['details']['tool']} ({a['details']['verdict']})",
                    "description": f"Isolation Forest 发现异常执行模式 (score={a['anomaly_score']})",
                    "evidence": a,
                    "proposed_change": {"add_to_baseline_gate": {"pattern": signature, "severity": 0.7}},
                    "impact_estimate": {"false_positive_risk": "high", "coverage_gain": "low"},
                    "status": "proposed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    else:
        print("   ⚠️  sklearn 未安装，跳过异常检测")

    # 5. 违规模式演变
    print("\n🔍 违规模式演变分析...")
    for v in violations:
        if v.get("evolution_stage") in ("new", "growing") and v.get("occurrence_count", 0) >= 5:
            signature = f"违规:{v.get('pattern_type','')}:{v.get('signature','')[:50]}"
            if not _check_existing_redline(signature):
                all_candidates.append({
                    "fuel_type": "redline_candidate",
                    "source": "violation_evolution",
                    "priority": 1,
                    "title": f"演变中违规模式: {v.get('pattern_type','')}",
                    "description": f"违规模式 {v.get('evolution_stage','')} (occurrences={v.get('occurrence_count',0)})",
                    "evidence": v,
                    "proposed_change": {"add_to_baseline_gate": {"pattern": signature, "severity": 0.9}},
                    "impact_estimate": {"false_positive_risk": "low", "coverage_gain": "high"},
                    "status": "proposed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

    # 去重
    seen = set()
    unique_candidates = []
    for c in all_candidates:
        key = c["title"][:100]
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    print(f"\n{'=' * 60}")
    print(f"发现红线候选: {len(unique_candidates)} (去重前: {len(all_candidates)})")
    print(f"{'=' * 60}")

    if args.dry_run:
        print("\n[dry-run] 候选预览:")
        for c in unique_candidates[:10]:
            print(f"  [{c['source']}] {c['title']}")
        return 0

    # 写入 evolution_fuel
    fuel_file = LAKE_ROOT / "analytics" / "evolution_fuel" / f"redline_candidates_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    fuel_file.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if fuel_file.exists():
        try:
            with open(fuel_file) as f:
                existing = json.load(f)
        except Exception:
            pass

    all_fuel = existing + unique_candidates
    with open(fuel_file, "w") as f:
        json.dump(all_fuel, f, indent=2, ensure_ascii=False)

    print(f"✅ 红线候选已写入: {fuel_file}")
    print(f"   总燃料数: {len(all_fuel)} (新增: {len(unique_candidates)})")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())