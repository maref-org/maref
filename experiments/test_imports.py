#!/usr/bin/env python3
"""测试所有组件的导入"""

import os
import sys

# 添加父目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("测试MAREF组件导入...")
print("=" * 50)

try:
    from maref_implementation.hexagram import Hexagram

    print("✓ Hexagram 导入成功")

    from maref_implementation.gray_code import GrayCodeTransformer

    print("✓ GrayCodeTransformer 导入成功")

    from maref_implementation.state_space import StateSpaceManager

    print("✓ StateSpaceManager 导入成功")

    from maref_implementation.three_talents_orchestrator import (
        MAREFWorkflowOrchestrator,
        get_maref_orchestrator,
    )

    print("✓ MAREFWorkflowOrchestrator 导入成功")

    from test_scenarios.baseline_scenario import run_baseline_scenario

    print("✓ baseline_scenario 导入成功")

    from test_scenarios.maref_scenario import run_maref_scenario

    print("✓ maref_scenario 导入成功")

    from validation_protocols.run_validation import ValidationController

    print("✓ ValidationController 导入成功")

    print("\n所有组件导入成功！")
    print("=" * 50)

except Exception as e:
    print(f"✗ 导入失败: {str(e)}")
    import traceback

    traceback.print_exc()
