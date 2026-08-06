#!/usr/bin/env python3
"""
简单测试 sidecar 启动和端点
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from maref.obs import MarefObsClient
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor
    from sidecar.obs_bridge import ObsBridge
    from sidecar.server import create_app
    
    print("✅ 依赖导入成功")
    
    # 创建依赖
    collector = ObservationCollector(adapter=MockAgentAdapter())
    monitor = CompositeMonitor()
    obs_bridge = None  # 先不启用遥测
    
    print("✅ 依赖创建成功")
    
    # 创建应用
    app = create_app(collector, monitor, obs_bridge=obs_bridge)
    print("✅ FastAPI 应用创建成功")
    
    # 测试路由
    print("\n可用路由:")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"  {route.path}")
    
    print("\n✅ sidecar 可以正常启动")
    print("\n要启动服务器，运行:")
    print("  uvicorn scripts.test_sidecar_simple:app --host 0.0.0.0 --port 8000 --reload")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("\n安装依赖:")
    print("  pip install -e . --break-system-packages")
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 创建全局应用实例
if 'app' in locals():
    # 导出应用实例
    pass