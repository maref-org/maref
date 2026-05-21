#!/usr/bin/env python3
"""
基线测试场景

运行当前Athena队列系统的精确模拟，重现5个系统性缺陷。
建立性能基准，用于与MAREF系统对比。

关键缺陷：
1. 任务身份规范化失败：ID以`-`开头被`argparse`误识别
2. Manifest数据质量缺陷：24%重复率，数据不一致
3. 进程可靠性契约缺失：先标记running再启动进程
4. 活跃占位检测延迟：死进程检测延迟5分钟
5. Lane混合与路由混淆：15%执行器混淆率
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# 添加父目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation_engine.athena_queue_simulator import run_baseline_simulation


def run_baseline_scenario(
    num_cycles: int = 5, tasks_per_cycle: int = 10, output_file: str = None
) -> Dict[str, Any]:
    """
    运行基线场景

    Args:
        num_cycles: 模拟周期数
        tasks_per_cycle: 每个周期的任务数
        output_file: 结果输出文件路径

    Returns:
        场景结果字典
    """
    print("=" * 70)
    print("基线场景 - Athena队列系统（当前有缺陷的版本）")
    print("=" * 70)

    start_time = time.time()

    # 记录场景配置
    scenario_config = {
        "scenario_name": "baseline_athena_queue",
        "num_cycles": num_cycles,
        "tasks_per_cycle": tasks_per_cycle,
        "start_time": datetime.now().isoformat(),
        "system_defects": [
            {
                "defect_id": "DF001",
                "name": "任务身份规范化失败",
                "description": "ID以`-`开头，被argparse误识别为flag参数",
                "severity": "HIGH",
                "probability": 0.3,
            },
            {
                "defect_id": "DF002",
                "name": "Manifest数据质量缺陷",
                "description": "24%重复条目，数据不一致",
                "severity": "MEDIUM",
                "impact": "资源浪费",
            },
            {
                "defect_id": "DF003",
                "name": "进程可靠性契约缺失",
                "description": "先标记running状态，再启动进程",
                "severity": "HIGH",
                "impact": "状态不一致，僵尸任务",
            },
            {
                "defect_id": "DF004",
                "name": "活跃占位检测延迟",
                "description": "死进程检测延迟5分钟",
                "severity": "MEDIUM",
                "impact": "资源浪费",
            },
            {
                "defect_id": "DF005",
                "name": "Lane混合与路由混淆",
                "description": "15%执行器选择混淆率",
                "severity": "MEDIUM",
                "impact": "执行结果不可预测",
            },
        ],
    }

    print(f"场景配置:")
    print(f"  周期数: {num_cycles}")
    print(f"  每周期任务数: {tasks_per_cycle}")
    print(f"  总任务数: ~{num_cycles * tasks_per_cycle}")

    # 运行基线模拟（当前使用内置的3周期，每周期5任务）
    # 在实际测试中可以扩展
    print("\n" + "=" * 40)
    print("开始基线模拟...")
    print("=" * 40)

    try:
        simulator, all_results, performance_summary = run_baseline_simulation()

        # 计算场景指标
        scenario_duration = time.time() - start_time

        # 计算缺陷影响指标
        defect_impacts = {
            "DF001_impact": performance_summary.get("task_id_normalization_errors", 0),
            "DF002_impact": performance_summary.get("manifest_duplicates_count", 0),
            "DF003_impact": performance_summary.get("process_reliability_errors", 0),
            "DF004_impact": performance_summary.get("stale_process_delay_seconds", 0),
            "DF005_impact": performance_summary.get("lane_confusion_rate_percent", 0),
        }

        # 构建场景结果
        scenario_result = {
            "scenario_config": scenario_config,
            "performance_summary": performance_summary,
            "defect_impacts": defect_impacts,
            "simulation_results": all_results,
            "metrics": {
                "total_tasks": performance_summary.get("total_tasks", 0),
                "successful_tasks": performance_summary.get("successful_tasks", 0),
                "failed_tasks": performance_summary.get("failed_tasks", 0),
                "task_success_rate": performance_summary.get("task_success_rate_percent", 0),
                "avg_completion_time_seconds": performance_summary.get(
                    "avg_completion_time_seconds", 0
                ),
                "avg_error_rate_percent": performance_summary.get("avg_error_rate_percent", 0),
                "avg_state_inconsistencies": performance_summary.get(
                    "avg_state_inconsistencies", 0
                ),
                "total_errors": performance_summary.get("total_errors", 0),
            },
            "timing": {
                "scenario_duration_seconds": scenario_duration,
                "tasks_per_second": (
                    performance_summary.get("total_tasks", 0) / scenario_duration
                    if scenario_duration > 0
                    else 0
                ),
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.now().isoformat(),
            },
            "system_defects_summary": {
                "total_defects": 5,
                "high_severity_defects": 2,
                "defect_manifestation_rate": sum(defect_impacts.values())
                / max(performance_summary.get("total_tasks", 1), 1),
                "overall_health_score": max(
                    0, 100 - performance_summary.get("avg_error_rate_percent", 0) * 2
                ),
            },
        }

        print("\n" + "=" * 40)
        print("基线场景完成")
        print("=" * 40)

        print(f"\n关键指标:")
        print(f"  任务成功率: {scenario_result['metrics']['task_success_rate']:.1f}%")
        print(f"  平均错误率: {scenario_result['metrics']['avg_error_rate_percent']:.1f}%")
        print(f"  平均完成时间: {scenario_result['metrics']['avg_completion_time_seconds']:.2f}秒")
        print(f"  状态不一致性: {scenario_result['metrics']['avg_state_inconsistencies']:.1f}")
        print(f"  总错误数: {scenario_result['metrics']['total_errors']}")

        print(f"\n缺陷影响:")
        for defect_id, impact in defect_impacts.items():
            defect_name = next(
                d["name"]
                for d in scenario_config["system_defects"]
                if d["defect_id"] == defect_id.split("_")[0]
            )
            print(f"  {defect_name}: {impact}")

        print(
            f"\n系统健康评分: {scenario_result['system_defects_summary']['overall_health_score']:.1f}/100"
        )

        # 保存结果到文件
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(scenario_result, f, indent=2, ensure_ascii=False)
            print(f"\n结果已保存到: {output_file}")

        return scenario_result

    except Exception as e:
        print(f"基线场景执行失败: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"error": str(e), "scenario_config": scenario_config, "success": False}


def analyze_baseline_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析基线结果，生成深入见解

    Args:
        results: 场景结果

    Returns:
        分析报告
    """
    if "error" in results:
        return {"error": "无法分析失败场景"}

    metrics = results["metrics"]
    defect_impacts = results["defect_impacts"]

    analysis = {
        "root_cause_analysis": {},
        "bottlenecks": [],
        "improvement_opportunities": [],
        "critical_issues": [],
    }

    # 根因分析
    error_rate = metrics["avg_error_rate_percent"]
    if error_rate > 20:
        analysis["root_cause_analysis"]["high_error_rate"] = {
            "primary_cause": "任务身份规范化失败和进程可靠性问题",
            "evidence": f"错误率高达{error_rate:.1f}%",
            "impact": "大量任务失败，系统不稳定",
        }

    # 瓶颈识别
    if metrics["avg_completion_time_seconds"] > 30:
        analysis["bottlenecks"].append(
            {
                "bottleneck": "死进程检测延迟",
                "impact": "资源长时间被占用",
                "recommendation": "减少心跳检测延迟，从5分钟降低到30秒",
            }
        )

    # 改进机会
    if defect_impacts.get("DF005_impact", 0) > 10:  # 混淆率>10%
        analysis["improvement_opportunities"].append(
            {
                "area": "执行器路由",
                "current_state": f"混淆率{defect_impacts.get('DF005_impact', 0):.1f}%",
                "potential_improvement": "引入智能路由决策，基于任务类型、资源需求、系统负载",
                "expected_impact": "减少50-80%的混淆",
            }
        )

    # 关键问题
    if metrics["avg_state_inconsistencies"] > 2:
        analysis["critical_issues"].append(
            {
                "issue": "状态不一致",
                "severity": "CRITICAL",
                "description": "Web界面、队列文件、manifest状态不同步",
                "recommendation": "实现原子状态更新和单一事实源",
            }
        )

    return analysis


if __name__ == "__main__":
    # 运行基线场景
    results = run_baseline_scenario(
        num_cycles=3, tasks_per_cycle=5, output_file="baseline_results.json"
    )

    # 分析结果
    if "error" not in results:
        analysis = analyze_baseline_results(results)
        print("\n" + "=" * 40)
        print("基线场景分析")
        print("=" * 40)

        if analysis.get("critical_issues"):
            print("\n关键问题:")
            for issue in analysis["critical_issues"]:
                print(f"  • {issue['issue']}: {issue['description']} (严重性: {issue['severity']})")
