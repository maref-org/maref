#!/usr/bin/env python3
"""快速测试基线场景和MAREF场景"""

import os
import sys

# 添加父目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_scenarios.baseline_scenario import run_baseline_scenario
from test_scenarios.maref_scenario import run_maref_scenario

print("快速测试MAREF验证系统")
print("=" * 50)

# 测试基线场景（小规模）
print("\n1. 测试基线场景（1周期，2任务）")
baseline_results = run_baseline_scenario(num_cycles=1, tasks_per_cycle=2, output_file=None)
if "error" in baseline_results:
    print(f"  错误: {baseline_results['error']}")
else:
    print(f"  成功! 创建任务: {baseline_results['metrics']['total_tasks']}")
    print(f"  任务成功率: {baseline_results['metrics']['task_success_rate']:.1f}%")
    print(f"  平均错误率: {baseline_results['metrics']['avg_error_rate_percent']:.1f}%")

# 测试MAREF场景（小规模）
print("\n2. 测试MAREF场景（1周期，2任务）")
maref_results = run_maref_scenario(num_cycles=1, tasks_per_cycle=2, output_file=None)
if "error" in maref_results:
    print(f"  错误: {maref_results['error']}")
else:
    print(f"  成功! 创建任务: {maref_results['metrics']['total_tasks']}")
    print(f"  任务成功率: {maref_results['metrics']['task_success_rate']:.1f}%")
    print(f"  平均错误率: {maref_results['metrics']['avg_error_rate_percent']:.1f}%")
    print(
        f"  MAREF健康评分: {maref_results['maref_system_health']['overall_health_score']:.1f}/100"
    )

print("\n" + "=" * 50)
print("快速测试完成")
