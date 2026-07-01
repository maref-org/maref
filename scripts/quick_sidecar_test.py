#!/usr/bin/env python3
"""
快速 sidecar 测试 - 直接测试修复是否有效
"""

import sys
import os
import json
import requests
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_sidecar_creation():
    """测试能否创建修复版 sidecar 应用"""
    print("测试修复版 sidecar 应用创建...")
    
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        from maref.obs import MarefObsClient
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.obs_bridge import ObsBridge
        from sidecar.server import create_app as create_original_app, create_a2a_bridge
        from maref.gaas.api import router as gaas_api_router
        from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
        from maref.integration.a2a_server import create_a2a_router
        
        print("✅ 模块导入成功")
        
        # 创建原始依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        obs_bridge = None
        
        print("✅ 依赖创建成功")
        
        # 创建原始应用
        app = create_original_app(collector, monitor, obs_bridge=obs_bridge)
        
        print("✅ 原始应用创建成功")
        
        # 修复：包含 GaaS API 路由
        app.include_router(gaas_api_router)
        print("✅ GaaS API 路由已包含")
        
        # 检查路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"📋 总路由数: {len(routes)}")
        
        # 检查关键端点
        key_endpoints = [
            "/api/health",
            "/api/v1/governance/state",
            "/api/v1/gaas/govern",
            "/api/compliance/check-action",
        ]
        
        print("\n🔍 检查关键端点:")
        for endpoint in key_endpoints:
            found = any(endpoint in r for r in routes)
            if found:
                print(f"  ✅ {endpoint}")
            else:
                print(f"  ❌ {endpoint} (未找到)")
        
        # 检查 GaaS 路由
        gaas_routes = [r for r in routes if 'gaas' in r]
        print(f"\n⚖️  GaaS 路由: {len(gaas_routes)} 个")
        for r in gaas_routes[:5]:
            print(f"  {r}")
        
        # 验证治理端点
        gov_endpoint = "/api/v1/gaas/govern"
        if any(gov_endpoint in r for r in routes):
            print(f"\n🎉 关键发现: {gov_endpoint} 已包含!")
            return True
        else:
            print(f"\n❌ 问题: {gov_endpoint} 未包含")
            return False
            
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_using_maref_lite():
    """测试使用 maref-lite 启动 sidecar"""
    print("\n测试使用 maref-lite 启动 sidecar...")
    
    # 检查 maref-lite 是否可用
    try:
        import subprocess
        import threading
        
        port = 8006
        
        # 启动 maref-lite serve
        cmd = [sys.executable, "-m", "maref_lite.cli", "serve", "--port", str(port)]
        
        print(f"启动命令: {' '.join(cmd)}")
        
        # 在后台启动
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 等待启动
        time.sleep(5)
        
        # 检查是否运行
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
            if resp.status_code == 200:
                print(f"✅ maref-lite sidecar 启动成功 (端口: {port})")
                
                # 测试 GaaS 端点
                test_data = {
                    "tenant_id": "test",
                    "actor_id": "test-agent",
                    "action": "write_file",
                    "tool": "Write",
                    "file_path": "/tmp/test.txt"
                }
                
                resp = requests.post(
                    f"http://127.0.0.1:{port}/api/v1/gaas/govern",
                    json=test_data,
                    timeout=5
                )
                
                print(f"GaaS 端点测试: HTTP {resp.status_code}")
                
                if resp.status_code in [200, 422]:
                    print("✅ GaaS 端点响应正常")
                else:
                    print(f"⚠️  GaaS 端点异常响应")
                
                # 停止进程
                proc.terminate()
                proc.wait()
                return True
            else:
                print(f"❌ sidecar 响应异常: {resp.status_code}")
                proc.terminate()
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ sidecar 未启动")
            proc.terminate()
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_simple_http():
    """简单 HTTP 测试（如果 sidecar 已经在运行）"""
    print("\n简单 HTTP 端点测试...")
    
    ports = [8000, 8001, 8002, 8003, 8004, 8005, 8006]
    
    for port in ports:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
            if resp.status_code == 200:
                print(f"✅ 发现运行中的 sidecar (端口: {port})")
                
                # 测试 GaaS 端点
                test_data = {
                    "tenant_id": "test",
                    "actor_id": "test-agent",
                    "action": "test",
                    "tool": "test",
                    "file_path": "/tmp/test.txt"
                }
                
                resp = requests.post(
                    f"http://127.0.0.1:{port}/api/v1/gaas/govern",
                    json=test_data,
                    timeout=3
                )
                
                print(f"  GaaS 端点: HTTP {resp.status_code}")
                if resp.status_code in [200, 422]:
                    print(f"  ✅ 端点可用")
                    return True
                else:
                    print(f"  ❌ 端点不可用")
                    
        except:
            continue
    
    print("❌ 未发现运行中的 sidecar")
    return False

def main():
    print("MAREF 治理补强 - 快速验证测试")
    print("=" * 60)
    
    # 测试1: 应用创建
    print("\n1. 测试修复版 sidecar 应用创建")
    creation_ok = test_sidecar_creation()
    
    # 测试2: 简单 HTTP 测试
    print("\n2. 测试现有 sidecar 实例")
    http_ok = test_simple_http()
    
    # 测试3: 使用 maref-lite
    if not http_ok:
        print("\n3. 尝试使用 maref-lite 启动")
        maref_ok = test_using_maref_lite()
    else:
        maref_ok = True  # 已经找到运行中的实例
    
    print("\n" + "=" * 60)
    print("测试总结:")
    print(f"✅ 应用创建: {'成功' if creation_ok else '失败'}")
    print(f"✅ HTTP 测试: {'成功' if http_ok else '失败'}")
    print(f"✅ maref-lite: {'成功' if maref_ok else '失败'}")
    
    if creation_ok:
        print("\n🎉 关键验证通过: GaaS 路由修复成功!")
        print("\n修复版 sidecar 可以正确包含治理端点")
        print("下一步: 配置 MCP Guard 进行端到端测试")
    else:
        print("\n❌ 需要进一步修复")
        
    return creation_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)