#!/usr/bin/env python3
"""
诊断 GaaS 端点 404 问题
"""

import sys
import os
import requests
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def check_maref_lite_sidecar():
    """检查 maref-lite 启动的 sidecar"""
    print("检查 maref-lite sidecar...")
    
    port = 8007
    
    # 启动 maref-lite
    cmd = [sys.executable, "-m", "maref_lite.cli", "serve", "--port", str(port)]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 等待启动
    time.sleep(5)
    
    try:
        # 测试健康端点
        health_resp = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
        print(f"健康端点: HTTP {health_resp.status_code}")
        
        if health_resp.status_code == 200:
            print(f"✅ sidecar 运行正常")
            
            # 列出所有端点
            print("\n测试端点列表:")
            endpoints = [
                ("/api/health", "GET"),
                ("/api/v1/governance/state", "GET"),
                ("/api/v1/gaas/govern", "POST"),
                ("/api/compliance/check-action", "POST"),
                ("/api/agents", "GET"),
                ("/api/v1/gaas/health", "GET"),  # GaaS 健康检查
                ("/api/gaas/", "GET"),  # 旧的 gaas_router 端点
            ]
            
            for path, method in endpoints:
                url = f"http://127.0.0.1:{port}{path}"
                try:
                    if method == "GET":
                        resp = requests.get(url, timeout=2)
                    else:
                        resp = requests.post(url, json={}, timeout=2)
                    
                    print(f"  {path}: HTTP {resp.status_code}")
                    
                    if resp.status_code == 404 and "gaas" in path:
                        print(f"    ⚠️  GaaS 端点 404")
                    elif resp.status_code == 200:
                        print(f"    ✅ 端点正常")
                        
                except Exception as e:
                    print(f"  {path}: 错误 - {str(e)[:50]}")
            
            # 详细检查 GaaS 端点
            print("\n详细检查 /api/v1/gaas/govern:")
            test_data = {
                "tenant_id": "test",
                "actor_id": "test-agent",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/tmp/test.txt",
                "metadata": {}
            }
            
            resp = requests.post(
                f"http://127.0.0.1:{port}/api/v1/gaas/govern",
                json=test_data,
                timeout=5
            )
            
            print(f"  状态码: {resp.status_code}")
            print(f"  响应头: {dict(resp.headers)}")
            if resp.content:
                print(f"  响应体: {resp.text[:200]}")
            
            # 检查是否包含 GaaS 路由
            print("\n检查路由包含情况:")
            try:
                from sidecar.server import create_app, create_a2a_bridge
                from sidecar.collector import MockAgentAdapter, ObservationCollector
                from sidecar.monitor import CompositeMonitor
                from maref.gaas.api import router as gaas_api_router
                
                collector = ObservationCollector(adapter=MockAgentAdapter())
                monitor = CompositeMonitor()
                app = create_app(collector, monitor)
                
                # 检查是否包含 gaas_api_router
                routes = []
                for route in app.routes:
                    if hasattr(route, 'path'):
                        routes.append(route.path)
                
                gaas_routes = [r for r in routes if 'gaas' in r]
                print(f"  sidecar 应用中的 GaaS 路由: {len(gaas_routes)} 个")
                
                # 检查 maref-lite 是否使用了修复
                print(f"  /api/v1/gaas/govern 在路由中: {'是' if any('/api/v1/gaas/govern' in r for r in routes) else '否'}")
                
            except Exception as e:
                print(f"  路由检查错误: {e}")
            
        else:
            print(f"❌ sidecar 健康检查失败")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    finally:
        # 停止进程
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
            print("✅ sidecar 已停止")

def check_gaas_api_directly():
    """直接检查 GaaS API 模块"""
    print("\n直接检查 GaaS API 模块...")
    
    try:
        from maref.gaas.api import router as gaas_api_router
        
        print(f"✅ GaaS API 路由器导入成功")
        print(f"  路由器前缀: {gaas_api_router.prefix}")
        print(f"  路由数量: {len(gaas_api_router.routes)}")
        
        # 显示路由
        for i, route in enumerate(gaas_api_router.routes[:5]):
            if hasattr(route, 'path'):
                print(f"  {i+1}. {route.path}")
        
        # 检查 /govern 路由
        govern_routes = [r for r in gaas_api_router.routes if hasattr(r, 'path') and '/govern' in r.path]
        if govern_routes:
            print(f"✅ 找到治理端点: {govern_routes[0].path}")
        else:
            print("❌ 未找到治理端点")
            
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
    except Exception as e:
        print(f"❌ 检查失败: {e}")

def check_sidecar_includes_gaas():
    """检查 sidecar 是否包含 GaaS 路由"""
    print("\n检查 sidecar 是否包含 GaaS 路由...")
    
    try:
        from sidecar.server import create_app, _setup_routes
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        app = create_app(collector, monitor)
        
        # 检查路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"sidecar 应用路由总数: {len(routes)}")
        
        # 检查 GaaS 路由
        gaas_routes = [r for r in routes if 'gaas' in r]
        print(f"GaaS 路由数量: {len(gaas_routes)}")
        
        if gaas_routes:
            print("找到的 GaaS 路由:")
            for r in gaas_routes[:10]:
                print(f"  {r}")
        
        # 检查 /api/v1/gaas/govern
        govern_exists = any('/api/v1/gaas/govern' in r for r in routes)
        print(f"/api/v1/gaas/govern 存在: {'✅ 是' if govern_exists else '❌ 否'}")
        
        # 检查 /api/gaas/ (旧的)
        old_gaas_exists = any('/api/gaas/' in r for r in routes)
        print(f"/api/gaas/ 存在: {'✅ 是' if old_gaas_exists else '❌ 否'}")
        
        return govern_exists
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("GaaS 端点 404 问题诊断")
    print("=" * 60)
    
    # 检查 GaaS API 模块
    check_gaas_api_directly()
    
    # 检查 sidecar 是否包含 GaaS
    sidecar_has_gaas = check_sidecar_includes_gaas()
    
    if sidecar_has_gaas:
        print("\n✅ sidecar 应用包含 GaaS 路由")
        print("问题可能在于:")
        print("1. maref-lite 使用了不同的应用实例")
        print("2. 路由注册顺序问题")
        print("3. 中间件配置问题")
    else:
        print("\n❌ sidecar 应用不包含 GaaS 路由")
        print("需要修复 sidecar 以包含 GaaS API 路由")
    
    # 检查 maref-lite 启动的实例
    print("\n" + "=" * 60)
    check_maref_lite_sidecar()
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("\n建议:")
    print("1. 检查 maref-lite 的 serve 命令实现")
    print("2. 确保修复被应用到实际启动的应用")
    print("3. 测试使用修复版 sidecar 启动脚本")

if __name__ == "__main__":
    main()