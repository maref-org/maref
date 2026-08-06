#!/usr/bin/env python3
"""
修复版 sidecar 启动器，确保包含 GaaS 路由
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maref.obs import MarefObsClient
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.obs_bridge import ObsBridge
from sidecar.server import create_app
from maref.gaas.api import router as gaas_api_router
from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
from maref.integration.a2a_bridge import create_a2a_bridge
from maref.integration.a2a_server import create_a2a_router

def create_fixed_app(collector: ObservationCollector, monitor: CompositeMonitor, obs_bridge: ObsBridge | None = None) -> FastAPI:
    """创建修复版应用，确保包含 GaaS API"""
    # 创建原始应用
    app = create_app(collector, monitor, obs_bridge=obs_bridge)
    
    # 确保包含 GaaS API 路由
    app.include_router(gaas_api_router)
    
    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 添加安全头部中间件
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 添加 A2A 路由
    a2a_bridge = create_a2a_bridge()
    _signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
    app.include_router(create_a2a_router(a2a_bridge, signing_key=_signing_key))
    
    return app

def main():
    port = 8000
    
    print(f"启动修复版 MAREF sidecar 服务器 (端口: {port})")
    print("=" * 50)
    
    try:
        # 创建依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        obs_bridge = None
        
        # 创建修复版应用
        app = create_fixed_app(collector, monitor, obs_bridge=obs_bridge)
        
        print("✅ 服务器已初始化")
        print(f"📊 健康检查: http://127.0.0.1:{port}/api/health")
        print(f"🔧 治理状态: http://127.0.0.1:{port}/api/v1/governance/state")
        print(f"⚖️  GaaS 端点: http://127.0.0.1:{port}/api/v1/gaas/govern")
        print(f"📋 代理列表: http://127.0.0.1:{port}/api/agents")
        print("=" * 50)
        
        # 检查 GaaS 路由
        gaas_routes = [r for r in app.routes if hasattr(r, 'path') and 'gaas' in r.path]
        print(f"找到 {len(gaas_routes)} 个 GaaS 路由")
        
        print("按 Ctrl+C 停止服务器")
        
        # 启动服务器
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()