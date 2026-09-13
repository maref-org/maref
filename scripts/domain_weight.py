#!/usr/bin/env python3
"""功能域权重分级告警 (P-05)"""
import json, os
from maref_config import config_path

AGENT_WEIGHTS = {
    "geo-orchestrator": 3,
    "evolution-daemon": 3,
    "intent-daemon": 3,
    "nightly-evolution": 3,
    "deepwater-guard": 4,
    "constitution-guard": 4,
    "proposal-watcher": 2,
    "heartbeat-monitor": 2,
    "audit-logger": 2,
    "default": 1
}


def _load_coding_agents():
    """从 coding_agents_registry.json 载入 coding agent 权重 (全域治理扩展)。"""
    from maref_config import REPO_DIR
    p = REPO_DIR / "configs" / "coding_agents_registry.json"
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            reg = json.load(f)
        return {a["agent_id"]: a.get("domain_weight", 2) for a in reg.get("agents", [])}
    except (json.JSONDecodeError, KeyError):
        return {}


def annotate_weights():
    coding = _load_coding_agents()
    all_weights = {**AGENT_WEIGHTS, **coding}

    print("=" * 60)
    print("功能域权重标注报告 (P-05)")
    print("=" * 60)

    weight_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for agent, weight in all_weights.items():
        if agent != "default":
            weight_counts[weight] = weight_counts.get(weight, 0) + 1

    print(f"\n--- 权重分布 ---")
    for w in sorted(weight_counts.keys(), reverse=True):
        level = {4: "constitutional", 3: "orchestrator", 2: "service", 1: "leaf"}[w]
        print(f"  weight={w} ({level}): {weight_counts[w]} agent")

    total_known = sum(weight_counts.values())
    print(f"  weight=1 (leaf): 按实际 agent 注册表动态扩展")
    print(f"  已标注治理角色: {len(AGENT_WEIGHTS) - 1} 个 (不含 default)")
    print(f"  已标注 coding agent: {len(coding)} 个 (Coding Agent 注册表)")
    print(f"  合计: {total_known} 个")
    print(f"  注: 原 139 总数为虚构，已按勘误声明（2026-09-11）移除")

    print(f"\n--- 域级告警规则 ---")
    print("  weight>=3 死亡/僵死 → 域级告警（推送 + 晨报置顶）")
    print("  weight=4 死亡 → nightly-evolution 当轮自动暂停")
    print("  weight<=2 → 现有温和提示")

    print(f"\n--- 编排者级 (weight=3) ---")
    for agent in all_weights:
        if all_weights[agent] == 3 and agent != "default":
            print(f"  {agent}")

    print(f"\n--- 守卫级 (weight=4) ---")
    for agent in all_weights:
        if all_weights[agent] == 4:
            print(f"  {agent}")

    print(f"\n--- 服务级 (weight=2) ---")
    for agent in all_weights:
        if all_weights[agent] == 2 and agent != "default":
            print(f"  {agent}")

    output_path = config_path("agent_domain_weights.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(all_weights, f, indent=2, ensure_ascii=False)
    print(f"\n权重配置已保存: {output_path}")

if __name__ == "__main__":
    annotate_weights()