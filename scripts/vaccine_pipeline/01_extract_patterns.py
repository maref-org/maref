#!/usr/bin/env python3
"""阶段1: 从红队日志提取攻击模式 (v2 — 多维度细化)"""
import json, os, hashlib
from collections import Counter, defaultdict

RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit.jsonl"
AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit_v2.jsonl"

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

def load_entries(path):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                pass
    return entries

def make_id(s):
    return hashlib.sha256(s.encode()).hexdigest()[:12]

def extract_sub_patterns(trips):
    patterns = []
    for action in sorted(set(t.get("action") for t in trips)):
        action_trips = [t for t in trips if t.get("action") == action]
        detail_groups = Counter(t.get("details", "") for t in action_trips)
        for detail, count in detail_groups.items():
            key = f"{action}::{detail}"
            patterns.append({
                "pattern_id": make_id(key),
                "attack_class": action,
                "attack_subtype": detail,
                "trigger": f"circuit_breaker_trip_{key.replace('::', '_').replace('=', '_')}",
                "count": count,
                "dimension": "action_detail",
            })
    return patterns

def extract_temporal_clusters(trips, window_seconds=60):
    sorted_trips = sorted(trips, key=lambda t: t.get("timestamp", 0))
    clusters = []
    current = []
    for t in sorted_trips:
        if not current:
            current = [t]
            continue
        gap = t.get("timestamp", 0) - current[-1].get("timestamp", 0)
        if gap <= window_seconds:
            current.append(t)
        else:
            if len(current) >= 3:
                actions = Counter(t.get("action") for t in current)
                key = "burst::" + "|".join(f"{a}x{c}" for a, c in actions.most_common(3))
                clusters.append({
                    "pattern_id": make_id(key),
                    "attack_class": "temporal_burst",
                    "attack_subtype": f"window_{window_seconds}s",
                    "trigger": f"clustered_trips_{len(current)}_in_{window_seconds}s",
                    "count": len(current),
                    "cluster_size": len(current),
                    "dimension": "temporal",
                })
            current = [t]
    if len(current) >= 3:
        clusters.append({
            "pattern_id": make_id(f"burst_final_{len(current)}"),
            "attack_class": "temporal_burst",
            "attack_subtype": f"window_{window_seconds}s",
            "trigger": f"clustered_trips_{len(current)}_in_{window_seconds}s",
            "count": len(current),
            "cluster_size": len(current),
            "dimension": "temporal",
        })
    return clusters

def extract_chain_patterns(trips):
    chains = []
    sorted_trips = sorted(trips, key=lambda t: t.get("timestamp", 0))
    for i in range(len(sorted_trips) - 1):
        gap = sorted_trips[i + 1].get("timestamp", 0) - sorted_trips[i].get("timestamp", 0)
        if gap <= 10:
            chain = (sorted_trips[i].get("action"), sorted_trips[i + 1].get("action"))
            chains.append(chain)
    chain_counts = Counter(chains)
    patterns = []
    for (a1, a2), count in chain_counts.most_common(10):
        if count >= 5:
            key = f"chain::{a1}->{a2}"
            patterns.append({
                "pattern_id": make_id(key),
                "attack_class": "attack_chain",
                "attack_subtype": f"{a1} → {a2}",
                "trigger": f"chain_{a1}_to_{a2}",
                "count": count,
                "dimension": "chain",
            })
    return patterns

def extract_anomaly_patterns():
    entries = load_entries(AUDIT_LOG)
    anomalies = [e for e in entries if e.get("event_type") == "anomaly_detected"]
    if not anomalies:
        return []
    verdicts = Counter(e.get("verdict", "unknown") for e in anomalies)
    patterns = []
    for v, count in verdicts.most_common():
        patterns.append({
            "pattern_id": make_id(f"anomaly_{v}"),
            "attack_class": "anomaly_detected",
            "attack_subtype": f"verdict={v}",
            "trigger": f"anomaly_verdict_{v}",
            "count": count,
            "dimension": "anomaly",
        })
    return patterns

def main():
    print("=" * 60)
    print("攻击模式抽取报告 (v2 — 多维度)")
    print("=" * 60)

    trips = [e for e in load_entries(RECURSIVE_LOG) if e.get("event_type") == "circuit_breaker_trip"]
    print(f"\n总 trip 条目: {len(trips)}")

    all_patterns = []

    sub = extract_sub_patterns(trips)
    print(f"\n--- 维度1: action × detail 细化 ---")
    print(f"提取模式: {len(sub)}")
    for p in sub:
        print(f"  {p['attack_class']}::{p['attack_subtype']} ({p['count']}x)")
    all_patterns.extend(sub)

    temporal = extract_temporal_clusters(trips)
    print(f"\n--- 维度2: 时间聚类 (60s窗口) ---")
    print(f"提取模式: {len(temporal)}")
    distinct = {}
    for p in temporal:
        key = p["trigger"]
        if key not in distinct:
            distinct[key] = p
    for p in distinct.values():
        print(f"  {p['trigger']} (cluster_size={p['cluster_size']}, {p['count']}x)")
    all_patterns.extend(list(distinct.values()))

    chains = extract_chain_patterns(trips)
    print(f"\n--- 维度3: 攻击链 (≤10s 连续) ---")
    print(f"提取模式: {len(chains)}")
    for p in chains:
        print(f"  {p['attack_subtype']} ({p['count']}x)")
    all_patterns.extend(chains)

    anomaly = extract_anomaly_patterns()
    print(f"\n--- 维度4: 异常检测模式 ---")
    print(f"提取模式: {len(anomaly)}")
    for p in anomaly:
        print(f"  {p['attack_subtype']} ({p['count']}x)")
    all_patterns.extend(anomaly)

    print(f"\n--- 维度5: OWASP 理论模式 ---")
    print(f"注入模式: {len(OWASP_PATTERNS)}")
    for p in OWASP_PATTERNS:
        p["pattern_id"] = make_id(p["trigger"])
        p["attack_class"] = p["class"]
        p["attack_subtype"] = "theoretical"
        p["count"] = 0
        p["dimension"] = "owasp_theoretical"
        all_patterns.append(p)
        print(f"  {p['attack_class']} (理论模式)")

    print(f"\n{'=' * 60}")
    print(f"总提取模式: {len(all_patterns)}")
    print(f"目标: ≥30")
    print(f"状态: {'✅ 达标' if len(all_patterns) >= 30 else '⚠️ 未达标'}")

    output_path = "/Volumes/1TB-M2/public/maref/scripts/vaccine_pipeline/patterns.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_patterns, f, indent=2, ensure_ascii=False)
    print(f"\n模式已保存: {output_path}")

if __name__ == "__main__":
    main()