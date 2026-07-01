#!/usr/bin/env python3
"""
修复 sidecar 的 GaaS 路由问题
在 sidecar 启动时包含 maref.gaas.api.router
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def create_fixed_app():
    """创建修复版 sidecar 应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from maref.obs import MarefObsClient
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor
    from sidecar.obs_bridge import ObsBridge
    from sidecar.server import create_app as create_original_app
    from maref.gaas.api import router as gaas_api_router
    from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
    from maref.integration.a2a_bridge import A2ABridge
    from maref.integration.a2a_server import create_a2a_router
    
    # 创建原始依赖
    collector = ObservationCollector(adapter=MockAgentAdapter())
    monitor = CompositeMonitor()
    obs_bridge = None
    
    # 创建原始应用
    app = create_original_app(collector, monitor, obs_bridge=obs_bridge)
    
    # 修复：包含 GaaS API 路由
    app.include_router(gaas_api_router)
    
    # 添加中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 添加 A2A 路由 - 使用 sidecar 中的 create_a2a_bridge 函数
    from sidecar.server import create_a2a_bridge
    a2a_bridge = create_a2a_bridge()
    signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
    app.include_router(create_a2a_router(a2a_bridge, signing_key=signing_key))
    
    return app

# 使用方式：
# 1. 保存此代码为 fixed_sidecar.py
# 2. 启动: uvicorn fixed_sidecar:create_fixed_app --host 0.0.0.0 --port 8000
# 3. 或集成到 maref-lite 中
