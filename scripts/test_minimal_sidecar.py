#!/usr/bin/env python3
"""
最小化 sidecar 测试
"""

import sys
import os
import time
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_sidecar_directly():
    """直接测试 sidecar 功能"""
    print("最小化 sidecar 测试")
    print("=" * 50)
    
    try:
        # 导入必要的模块
        from maref.obs import MarefObsClient
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.obs_bridge import ObsBridge
        from sidecar.server import create_app
        
        print("✅ 模块导入成功")
        
        # 创建依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        
        print("✅ 依赖创建成功")
        
        # 创建应用
        app = create_app(collector, monitor)
        
        print("✅ FastAPI 应用创建成功")
        
        # 检查路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"\n📋 找到 {len(routes)} 个路由")
        
        # 检查关键端点
        key_endpoints = [
            "/api/health",
            "/api/v1/governance/state", 
            "/api/v1/gaas/govern",
            "/api/compliance/check-action",
            "/api/agents"
        ]
        
        print("\n🔍 检查关键端点:")
        for endpoint in key_endpoints:
            found = any(endpoint in r for r in routes)
            if found:
                print(f"  ✅ {endpoint}")
            else:
                print(f"  ❌ {endpoint} (未找到)")
        
        # 检查 GaaS 端点
        gaas_routes = [r for r in routes if 'gaas' in r]
        print(f"\n⚖️  GaaS 路由: {len(gaas_routes)} 个")
        for r in gaas_routes[:5]:  # 只显示前5个
            print(f"  {r}")
        if len(gaas_routes) > 5:
            print(f"  ... 还有 {len(gaas_routes)-5} 个")
        
        # 检查治理端点
        gov_routes = [r for r in routes if 'governance' in r]
        print(f"\n🔧 治理路由: {len(gov_routes)} 个")
        for r in gov_routes:
            print(f"  {r}")
        
        print("\n" + "=" * 50)
        print("结论:")
        
        if "/api/v1/gaas/govern" in str(routes):
            print("✅ GaaS 治理端点已包含")
        else:
            print("❌ GaaS 治理端点未包含")
            print("建议: 确保 sidecar 包含了 gaas_api_router")
        
        if len(gov_routes) > 0:
            print("✅ 治理路由已配置")
        else:
            print("❌ 治理路由未配置")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_quick_start():
    """快速启动测试"""
    print("\n" + "=" * 50)
    print("快速启动测试")
    print("=" * 50)
    
    # 检查是否可以通过 uvicorn 启动
    import subprocess
    import threading
    import atexit
    
    port = 8003
    
    def run_server():
        cmd = [
            sys.executable, "-m", "uvicorn",
            "sidecar.server:create_app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--log-level", "warning"
        ]
        
        # 设置环境变量
        env = os.environ.copy()
        
        # 运行服务器
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 注册退出时清理
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
        
        atexit.register(cleanup)
        
        # 等待启动
        time.sleep(3)
        
        # 检查是否运行
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
            if resp.status_code == 200:
                print(f"✅ 服务器在端口 {port} 启动成功")
                print(f"   健康状态: {resp.json().get('status', 'unknown')}")
                return proc, True
            else:
                print(f"❌ 服务器响应异常: HTTP {resp.status_code}")
                cleanup()
                return None, False
        except:
            print(f"❌ 服务器启动失败")
            cleanup()
            return None, False
    
    print(f"尝试在端口 {port} 启动服务器...")
    proc, success = run_server()
    
    if success and proc:
        print("\n✅ 快速启动测试通过")
        print(f"   服务器 PID: {proc.pid}")
        print(f"   停止命令: kill {proc.pid}")
        
        # 测试其他端点
        print("\n测试其他端点:")
        endpoints = [
            ("/api/v1/governance/state", "GET"),
            ("/api/agents", "GET"),
        ]
        
        for path, method in endpoints:
            try:
                url = f"http://127.0.0.1:{port}{path}"
                if method == "GET":
                    resp = requests.get(url, timeout=2)
                else:
                    resp = requests.post(url, timeout=2)
                
                if resp.status_code == 200:
                    print(f"  ✅ {path}: HTTP {resp.status_code}")
                else:
                    print(f"  ⚠️  {path}: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  ❌ {path}: {str(e)[:50]}")
        
        # 清理
        proc.terminate()
        proc.wait()
        print("\n✅ 服务器已停止")
        
        return True
    else:
        print("❌ 快速启动测试失败")
        return False

def main():
    print("MAREF Sidecar 功能测试")
    print("=" * 50)
    
    # 测试1: 直接功能测试
    test1_success = test_sidecar_directly()
    
    # 测试2: 快速启动测试
    test2_success = test_quick_start()
    
    print("\n" + "=" * 50)
    print("最终结果:")
    
    if test1_success and test2_success:
        print("✅ 所有测试通过")
        print("\n下一步:")
        print("1. 使用修复版 sidecar 启动器")
        print("2. 测试端点响应")
        print("3. 开始 Phase 2 开发")
    elif test1_success:
        print("⚠️  基本功能正常，但启动测试失败")
        print("\n建议:")
        print("1. 检查 uvicorn 安装")
        print("2. 检查端口冲突")
        print("3. 查看详细错误日志")
    else:
        print("❌ 基本功能测试失败")
        print("\n建议:")
        print("1. 检查 MAREF 安装")
        print("2. 检查 Python 路径")
        print("3. 查看导入错误详情")

if __name__ == "__main__":
    main()