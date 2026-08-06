#!/usr/bin/env python3
"""
测试修复版 sidecar 的端点
"""

import sys
import os
import time
import threading
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def start_sidecar_in_thread(port=8002):
    """在后台线程中启动 sidecar"""
    import uvicorn
    from maref.obs import MarefObsClient
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor
    from sidecar.obs_bridge import ObsBridge
    from sidecar.server import create_app
    from maref.gaas.api import router as gaas_api_router
    from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
    from maref.integration.a2a_bridge import create_a2a_bridge
    from maref.integration.a2a_server import create_a2a_router
    from fastapi.middleware.cors import CORSMiddleware
    
    def run():
        # 创建依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        
        # 创建应用
        app = create_app(collector, monitor)
        
        # 确保包含 GaaS API 路由
        app.include_router(gaas_api_router)
        
        # 启动服务器
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread

def test_endpoint(url, method="GET", data=None, timeout=5):
    """测试端点"""
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        else:
            resp = requests.post(url, json=data, timeout=timeout)
        return {
            "success": True,
            "status": resp.status_code,
            "data": resp.json() if resp.content else {}
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main():
    port = 8002
    base_url = f"http://127.0.0.1:{port}"
    
    print("测试修复版 sidecar 端点")
    print("=" * 50)
    
    # 启动 sidecar
    print("启动 sidecar...")
    thread = start_sidecar_in_thread(port)
    
    # 等待服务器启动
    print("等待服务器启动...")
    time.sleep(3)
    
    # 测试端点
    endpoints = [
        ("/api/health", "GET"),
        ("/api/v1/governance/state", "GET"),
        ("/api/v1/gaas/govern", "POST", {"tenant_id": "test", "actor_id": "test-agent", "action": "test"}),
        ("/api/compliance/check-action", "POST", {"agent_id": "test", "action": "test"}),
        ("/api/agents", "GET"),
    ]
    
    results = []
    for endpoint in endpoints:
        path = endpoint[0]
        method = endpoint[1]
        data = endpoint[2] if len(endpoint) > 2 else None
        
        url = f"{base_url}{path}"
        print(f"\n测试 {method} {path}...")
        
        result = test_endpoint(url, method, data, timeout=3)
        
        if result["success"]:
            status = result["status"]
            if status == 200:
                print(f"  ✅ HTTP {status}")
                # 显示关键字段
                if path == "/api/health":
                    data = result.get("data", {})
                    print(f"     状态: {data.get('status', 'N/A')}")
                elif path == "/api/v1/governance/state":
                    data = result.get("data", {})
                    print(f"     治理状态: {data.get('state', 'N/A')}")
            elif status == 404:
                print(f"  ⚠️  HTTP {status} (端点未找到)")
            elif status == 422:
                print(f"  ⚠️  HTTP {status} (参数验证失败)")
            else:
                print(f"  ❓ HTTP {status}")
        else:
            print(f"  ❌ 错误: {result['error']}")
        
        results.append((path, result))
    
    print("\n" + "=" * 50)
    print("测试总结:")
    
    success_count = sum(1 for _, r in results if r.get("success") and r.get("status", 0) in [200, 422])
    total_count = len(results)
    
    print(f"成功: {success_count}/{total_count}")
    
    # 检查关键端点
    key_endpoints = {
        "/api/health": "健康检查",
        "/api/v1/governance/state": "治理状态",
        "/api/v1/gaas/govern": "GaaS 治理",
    }
    
    print("\n关键端点状态:")
    for path, name in key_endpoints.items():
        for ep_path, result in results:
            if ep_path == path:
                if result.get("success"):
                    status = result.get("status", 0)
                    if status in [200, 422]:
                        print(f"  ✅ {name}: 可用 (HTTP {status})")
                    else:
                        print(f"  ⚠️  {name}: 异常 (HTTP {status})")
                else:
                    print(f"  ❌ {name}: 不可用")
                break
    
    print("\n建议:")
    if success_count >= 2:
        print("✅ sidecar 基本功能正常，可以继续开发")
    else:
        print("❌ sidecar 存在问题，需要进一步调试")
    
    # 保持线程运行
    print("\n按 Ctrl+C 停止服务器")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止服务器...")

if __name__ == "__main__":
    main()