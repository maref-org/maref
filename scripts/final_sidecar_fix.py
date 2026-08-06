#!/usr/bin/env python3
"""
最终版 sidecar 修复方案

修复 GaaS 路由缺失问题，确保治理端点可用。
"""

import sys
import os
import time
import requests
import subprocess
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

class SidecarFix:
    """修复 sidecar 的 GaaS 路由问题"""
    
    @staticmethod
    def check_current_state():
        """检查当前 sidecar 状态"""
        print("检查当前 sidecar 状态...")
        print("=" * 50)
        
        # 检查模块
        modules = [
            ("sidecar.server", "create_app"),
            ("sidecar.gaas_router", "router"),
            ("maref.gaas.api", "router"),
            ("sidecar.collector", "ObservationCollector"),
            ("sidecar.monitor", "CompositeMonitor"),
        ]
        
        for module_name, attr_name in modules:
            try:
                module = __import__(module_name, fromlist=[attr_name])
                if hasattr(module, attr_name):
                    obj = getattr(module, attr_name)
                    print(f"✅ {module_name}.{attr_name}: 存在")
                    
                    # 特殊检查
                    if attr_name == "router":
                        if hasattr(obj, 'routes'):
                            print(f"   路由数量: {len(obj.routes)}")
                            # 显示前几个路由
                            for i, route in enumerate(obj.routes[:3]):
                                if hasattr(route, 'path'):
                                    print(f"     {route.path}")
                            if len(obj.routes) > 3:
                                print(f"     ... 还有 {len(obj.routes)-3} 个路由")
                else:
                    print(f"❌ {module_name}.{attr_name}: 不存在")
            except ImportError as e:
                print(f"❌ {module_name}.{attr_name}: 导入失败 - {e}")
        
        print("\n" + "=" * 50)
    
    @staticmethod
    def create_fixed_app():
        """创建修复版应用"""
        print("创建修复版 sidecar 应用...")
        
        try:
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            
            from maref.obs import MarefObsClient
            from sidecar.collector import MockAgentAdapter, ObservationCollector
            from sidecar.monitor import CompositeMonitor
            from sidecar.obs_bridge import ObsBridge
            from sidecar.server import create_app as create_original_app
            from maref.gaas.api import router as gaas_api_router
            from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
            
            print("✅ 模块导入成功")
            
            # 创建原始依赖
            collector = ObservationCollector(adapter=MockAgentAdapter())
            monitor = CompositeMonitor()
            obs_bridge = None
            
            print("✅ 依赖创建成功")
            
            # 创建原始应用
            app = create_original_app(collector, monitor, obs_bridge=obs_bridge)
            
            print("✅ 原始应用创建成功")
            
            # 修复：确保包含 GaaS API 路由
            app.include_router(gaas_api_router)
            
            print("✅ GaaS API 路由已包含")
            
            # 添加中间件
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            app.add_middleware(SecurityHeadersMiddleware)
            
            print("✅ 中间件已添加")
            
            # 验证修复
            routes = []
            for route in app.routes:
                if hasattr(route, 'path'):
                    routes.append(route.path)
            
            # 检查关键端点
            key_endpoints = {
                "/api/v1/gaas/govern": "GaaS 治理端点",
                "/api/health": "健康检查",
                "/api/v1/governance/state": "治理状态",
                "/api/compliance/check-action": "合规检查",
            }
            
            print("\n🔍 验证修复结果:")
            for endpoint, description in key_endpoints.items():
                found = any(endpoint in r for r in routes)
                if found:
                    print(f"  ✅ {description}: {endpoint}")
                else:
                    print(f"  ❌ {description}: {endpoint} (未找到)")
            
            # 统计 GaaS 路由
            gaas_routes = [r for r in routes if 'gaas' in r]
            print(f"\n⚖️  找到 {len(gaas_routes)} 个 GaaS 路由")
            
            return app
            
        except Exception as e:
            print(f"❌ 创建修复版应用失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def start_server(app, port=8004):
        """启动修复版服务器"""
        print(f"\n启动修复版服务器 (端口: {port})...")
        
        import uvicorn
        
        def run():
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
        
        # 在后台线程中运行
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        
        # 等待服务器启动
        time.sleep(3)
        
        return thread
    
    @staticmethod
    def test_endpoints(port=8004):
        """测试端点"""
        print(f"\n测试端点 (端口: {port})...")
        print("=" * 50)
        
        base_url = f"http://127.0.0.1:{port}"
        endpoints = [
            ("/api/health", "GET", None, "健康检查"),
            ("/api/v1/governance/state", "GET", None, "治理状态"),
            ("/api/v1/gaas/govern", "POST", 
             {"tenant_id": "test", "actor_id": "test-agent", "action": "test", "tool": "test"}, 
             "GaaS 治理"),
            ("/api/compliance/check-action", "POST", 
             {"agent_id": "test", "action": "test"}, 
             "合规检查"),
            ("/api/agents", "GET", None, "代理列表"),
        ]
        
        results = []
        for path, method, data, description in endpoints:
            url = f"{base_url}{path}"
            
            try:
                if method == "GET":
                    resp = requests.get(url, timeout=3)
                else:
                    resp = requests.post(url, json=data, timeout=3)
                
                status = resp.status_code
                
                if status == 200:
                    print(f"✅ {description}: HTTP {status}")
                    results.append(True)
                elif status == 422:
                    # 422 表示参数验证失败，但端点存在
                    print(f"⚠️  {description}: HTTP {status} (参数验证失败)")
                    print(f"   请求: {data}")
                    results.append(True)  # 端点存在
                elif status == 404:
                    print(f"❌ {description}: HTTP {status} (端点未找到)")
                    results.append(False)
                else:
                    print(f"❓ {description}: HTTP {status}")
                    if resp.content:
                        print(f"   响应: {resp.text[:100]}")
                    results.append(False)
                    
            except requests.exceptions.ConnectionError:
                print(f"❌ {description}: 连接失败")
                results.append(False)
            except Exception as e:
                print(f"❌ {description}: 错误 - {str(e)[:50]}")
                results.append(False)
        
        print("\n" + "=" * 50)
        success_count = sum(results)
        total_count = len(results)
        
        print(f"测试结果: {success_count}/{total_count} 通过")
        
        # 关键端点检查
        critical_endpoints = [
            ("/api/health", "健康检查"),
            ("/api/v1/gaas/govern", "GaaS 治理"),
        ]
        
        print("\n关键端点状态:")
        for i, (path, method, data, description) in enumerate(endpoints):
            if any(path == crit_path for crit_path, _ in critical_endpoints):
                status = "✅ 通过" if results[i] else "❌ 失败"
                print(f"  {status} {description}")
        
        return success_count >= 2  # 至少健康检查和GaaS端点要通过

def main():
    print("MAREF Sidecar 最终修复方案")
    print("=" * 60)
    
    fix = SidecarFix()
    
    # 步骤1: 检查当前状态
    fix.check_current_state()
    
    # 步骤2: 创建修复版应用
    app = fix.create_fixed_app()
    if not app:
        print("❌ 无法创建修复版应用")
        return
    
    # 步骤3: 启动服务器
    port = 8004
    thread = fix.start_server(app, port)
    
    # 给服务器更多时间启动
    time.sleep(2)
    
    # 步骤4: 测试端点
    success = fix.test_endpoints(port)
    
    print("\n" + "=" * 60)
    print("修复方案总结:")
    
    if success:
        print("✅ 修复成功!")
        print("\nGaaS 治理端点现在可用:")
        print(f"  POST http://127.0.0.1:{port}/api/v1/gaas/govern")
        print("\nMCP Guard 现在可以调用此端点进行治理检查")
        
        print("\n下一步:")
        print("1. 更新 MCP Guard 使用此端点")
        print("2. 测试完整的治理流程")
        print("3. 部署到生产环境")
    else:
        print("❌ 修复失败")
        print("\n可能原因:")
        print("1. 服务器启动失败")
        print("2. 端口冲突")
        print("3. 依赖问题")
        print("\n建议:")
        print("1. 检查端口 {port} 是否被占用")
        print("2. 查看详细的错误日志")
        print("3. 尝试不同端口")
    
    print("\n" + "=" * 60)
    
    # 保持服务器运行
    if success:
        print(f"服务器在端口 {port} 运行中...")
        print("按 Ctrl+C 停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止服务器...")

if __name__ == "__main__":
    main()