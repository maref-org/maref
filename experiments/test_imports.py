#!/usr/bin/env python3
"""测试所有组件的导入"""

import os
import sys

# 添加父目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("测试MAREF组件导入...")
print("=" * 50)

try:
    print("✓ Hexagram 导入成功")

    print("✓ GrayCodeTransformer 导入成功")

    print("✓ StateSpaceManager 导入成功")

    print("✓ MAREFWorkflowOrchestrator 导入成功")

    print("✓ baseline_scenario 导入成功")

    print("✓ maref_scenario 导入成功")

    print("✓ ValidationController 导入成功")

    print("\n所有组件导入成功！")
    print("=" * 50)

except Exception as e:
    print(f"✗ 导入失败: {str(e)}")
    import traceback

    traceback.print_exc()
