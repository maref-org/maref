#!/usr/bin/env python3
"""
诊断和修复 sidecar 的 GaaS 路由问题
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def diagnose():
    """诊断问题"""
    print("诊断 MAREF sidecar GaaS 路由问题")
    print("=" * 60)
    
    problems = []
    
    # 1. 检查 gaas_router
    try:
        from sidecar.gaas_router import router as gaas_router
        print(f"1. sidecar.gaas_router: ✅ 存在")
        print(f"   前缀: {gaas_router.prefix}")
        print(f"   路由数量: {len(gaas_router.routes)}")
        
        if len(gaas_router.routes) == 0:
            problems.append("sidecar.gaas_router 是空的")
            print("   ❌ 问题: 路由器是空的")
    except ImportError as e:
        problems.append(f"无法导入 sidecar.gaas_router: {e}")
        print(f"1. sidecar.gaas_router: ❌ 导入失败 - {e}")
    
    # 2. 检查 gaas_api_router
    try:
        from maref.gaas.api import router as gaas_api_router
        print(f"\n2. maref.gaas.api.router: ✅ 存在")
        print(f"   前缀: {gaas_api_router.prefix}")
        print(f"   路由数量: {len(gaas_api_router.routes)}")
        
        # 显示关键路由
        gov_route = None
        for route in gaas_api_router.routes:
            if hasattr(route, 'path'):
                path = route.path
                if '/govern' in path:
                    gov_route = path
                print(f"     {path}")
        
        if gov_route:
            print(f"\n   ✅ 找到治理端点: {gov_route}")
        else:
            problems.append("gaas_api_router 中没有治理端点")
            print("   ❌ 问题: 没有治理端点")
            
    except ImportError as e:
        problems.append(f"无法导入 maref.gaas.api: {e}")
        print(f"\n2. maref.gaas.api.router: ❌ 导入失败 - {e}")
    
    # 3. 检查 sidecar 服务器
    try:
        from sidecar.server import create_app, _setup_routes
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        
        print(f"\n3. sidecar.server: ✅ 可导入")
        
        # 创建测试应用
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        app = create_app(collector, monitor)
        
        # 检查路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"   应用路由数量: {len(routes)}")
        
        # 检查是否包含 GaaS 路由
        gaas_routes = [r for r in routes if 'gaas' in r]
        if gaas_routes:
            print(f"   ✅ 包含 GaaS 路由: {len(gaas_routes)} 个")
            for r in gaas_routes[:3]:
                print(f"     {r}")
        else:
            problems.append("sidecar 应用不包含 GaaS 路由")
            print("   ❌ 问题: 不包含 GaaS 路由")
        
        # 检查治理端点
        gov_endpoints = [r for r in routes if '/govern' in r]
        if gov_endpoints:
            print(f"   ✅ 包含治理端点: {len(gov_endpoints)} 个")
            for r in gov_endpoints:
                print(f"     {r}")
        else:
            problems.append("sidecar 应用不包含治理端点")
            print("   ❌ 问题: 不包含治理端点")
            
    except ImportError as e:
        problems.append(f"无法导入 sidecar.server: {e}")
        print(f"\n3. sidecar.server: ❌ 导入失败 - {e}")
    except Exception as e:
        problems.append(f"创建测试应用失败: {e}")
        print(f"\n3. sidecar.server: ❌ 测试失败 - {e}")
    
    print("\n" + "=" * 60)
    print("诊断结果:")
    
    if problems:
        print(f"❌ 发现 {len(problems)} 个问题:")
        for i, problem in enumerate(problems, 1):
            print(f"  {i}. {problem}")
        return False, problems
    else:
        print("✅ 所有检查通过")
        return True, []

def create_fix():
    """创建修复"""
    print("\n" + "=" * 60)
    print("创建修复方案")
    print("=" * 60)
    
    fix_code = '''#!/usr/bin/env python3
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
    
    # 添加 A2A 路由
    a2a_bridge = A2ABridge()
    signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
    app.include_router(create_a2a_router(a2a_bridge, signing_key=signing_key))
    
    return app

# 使用方式：
# 1. 保存此代码为 fixed_sidecar.py
# 2. 启动: uvicorn fixed_sidecar:create_fixed_app --host 0.0.0.0 --port 8000
# 3. 或集成到 maref-lite 中
'''
    
    # 写入修复文件
    fix_path = os.path.join(os.path.dirname(__file__), 'fixed_sidecar.py')
    with open(fix_path, 'w') as f:
        f.write(fix_code)
    
    print(f"✅ 修复代码已写入: {fix_path}")
    
    # 创建启动脚本
    start_script = '''#!/usr/bin/env python3
"""
启动修复版 sidecar
"""

import subprocess
import sys
import os

# 启动修复版 sidecar
port = 8000
cmd = [
    sys.executable, "-m", "uvicorn",
    "fixed_sidecar:create_fixed_app",
    "--host", "0.0.0.0",
    "--port", str(port),
    "--reload"
]

print(f"启动修复版 sidecar (端口: {port})...")
print(f"命令: {' '.join(cmd)}")
print(f"健康检查: http://127.0.0.1:{port}/api/health")
print(f"GaaS 治理: http://127.0.0.1:{port}/api/v1/gaas/govern")

subprocess.run(cmd)
'''
    
    start_path = os.path.join(os.path.dirname(__file__), 'start_fixed_sidecar.py')
    with open(start_path, 'w') as f:
        f.write(start_script)
    
    print(f"✅ 启动脚本已写入: {start_path}")
    
    print("\n修复方案:")
    print("1. 使用 fixed_sidecar.py 作为修复版 sidecar")
    print("2. 使用 start_fixed_sidecar.py 启动")
    print("3. 或修改 maref-lite 以包含此修复")
    
    return True

def create_mcp_guard_config():
    """创建 MCP Guard 配置"""
    print("\n" + "=" * 60)
    print("创建 MCP Guard 配置")
    print("=" * 60)
    
    # Trae 配置
    trae_config = {
        "mcpServers": {
            "maref-governance": {
                "command": "python3",
                "args": [
                    os.path.join(os.path.dirname(__file__), "simple_mcp_guard.py")
                ],
                "env": {
                    "MAREF_AGENT_ID": "trae-cn",
                    "MAREF_SIDECAR_URL": "http://127.0.0.1:8000",
                    "MAREF_API_KEY": "test-key"
                }
            }
        }
    }
    
    import json
    trae_path = os.path.join(os.path.dirname(__file__), 'trae_mcp_config.json')
    with open(trae_path, 'w') as f:
        json.dump(trae_config, f, indent=2)
    
    print(f"✅ Trae MCP 配置: {trae_path}")
    
    # OpenCode 配置
    opencode_config = {
        "mcpServers": {
            "maref-governance": {
                "command": "python3",
                "args": [
                    "scripts/simple_mcp_guard.py"
                ],
                "env": {
                    "MAREF_AGENT_ID": "opencode",
                    "MAREF_SIDECAR_URL": "http://127.0.0.1:8000",
                    "MAREF_API_KEY": "test-key"
                }
            }
        }
    }
    
    opencode_path = os.path.join(os.path.dirname(__file__), '../opencode.json')
    with open(opencode_path, 'w') as f:
        json.dump(opencode_config, f, indent=2)
    
    print(f"✅ OpenCode MCP 配置: {opencode_path}")
    
    print("\n配置说明:")
    print("1. Trae: 复制 trae_mcp_config.json 到 ~/.trae/mcp_config.json")
    print("2. OpenCode: opencode.json 会自动在项目根目录被发现")
    print("3. 重启 IDE 以加载配置")

def main():
    print("MAREF 治理补强工程 - 诊断与修复")
    print("=" * 60)
    
    # 诊断
    success, problems = diagnose()
    
    if not success:
        print("\n" + "=" * 60)
        print("需要修复的问题:")
        for problem in problems:
            print(f"  • {problem}")
    
    # 创建修复
    if create_fix():
        print("\n✅ 修复方案已创建")
    
    # 创建 MCP Guard 配置
    create_mcp_guard_config()
    
    print("\n" + "=" * 60)
    print("下一步行动:")
    print("1. 启动修复版 sidecar:")
    print("   python3 scripts/start_fixed_sidecar.py")
    print("2. 配置 Trae/OpenCode 使用 MCP Guard")
    print("3. 测试治理拦截功能")
    print("4. 验证审计数据生成")
    print("\n目标: 将治理覆盖率从 0% 提升到 >80%")

if __name__ == "__main__":
    main()