#!/usr/bin/env python3
"""
修复版 maref-lite serve 命令
确保包含 GaaS 路由
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.dirname(__file__))  # scripts directory for sibling imports

import uvicorn
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="HTTP server port"),
    gui: bool = typer.Option(False, "--gui/--no-gui", help="Enable GUI endpoints"),
    telemetry: bool = typer.Option(False, "--telemetry/--no-telemetry", help="Enable telemetry bridge"),
) -> None:
    """启动修复版 MAREF Sidecar HTTP server（包含 GaaS 路由）"""
    if gui:
        console.print("[bold green]MAREF Sidecar Server (GUI Mode)[/bold green]")
    else:
        console.print("[bold green]MAREF Sidecar Server (修复版)[/bold green]")
    
    console.print(f"Starting on http://0.0.0.0:{port}")
    console.print(f"  [green]Health:[/green]     http://localhost:{port}/api/health")
    console.print(f"  [green]GaaS Govern:[/green] http://localhost:{port}/api/v1/gaas/govern")
    console.print(f"  [green]Agents:[/green]     http://localhost:{port}/api/agents")
    
    if gui:
        console.print(f"  [green]Sessions:[/green]   http://localhost:{port}/api/sessions")
    
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
        
        # 创建依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        obs_bridge = ObsBridge(client=MarefObsClient.get_default()) if telemetry else None
        
        # 创建原始应用
        app = create_original_app(collector, monitor, obs_bridge=obs_bridge)
        
        # 🎯 修复：包含 GaaS API 路由
        app.include_router(gaas_api_router)
        console.print("  [green]✅ GaaS 路由已包含[/green]")
        
        # 🎯 注册默认租户（用于认证）
        from maref.gaas.tenant import Tenant, TenantManager
        from maref.gaas.api import get_tenant_manager
        
        tm = get_tenant_manager()
        default_tenant = Tenant(
            tenant_id="default",
            name="Default Tenant",
            tier="enterprise"
        )
        
        # 检查是否已注册
        if not tm.get_by_id("default"):
            api_key = tm.register(default_tenant, api_key="default-key")
            console.print(f"  [green]✅ 默认租户已注册[/green]")
            console.print(f"     API Key: {api_key}")
        else:
            console.print(f"  [green]✅ 默认租户已存在[/green]")
        
        # 🎯 注册 Agent 信任评分
        from maref.gaas.api import get_trust_service, get_governance_router
        trust_svc = get_trust_service()
        known_agents = [
            ("trae-cn", "Trae IDE Agent (CN)"),
            ("opencode", "OpenCode CLI Agent"),
            ("cursor", "Cursor IDE Agent"),
        ]
        for agent_id, desc in known_agents:
            current = trust_svc.get_score("default", agent_id)
            if current is None:
                trust_svc.set_score("default", agent_id, 50.0, reason="initial_registration")
                console.print(f"  [green]✅ Agent 已注册:[/green] {agent_id} ({desc}, trust=50.0)")
            else:
                console.print(f"  [green]✅ Agent 已存在:[/green] {agent_id} (trust={current:.1f})")
        
        # 🎯 注入统一审计桥（替换 mock 数据）
        try:
            from unified_audit_bridge import inject_into_sidecar
            inject_into_sidecar(app)
            console.print("  [green]✅ 统一审计桥已注入[/green]")
        except Exception as e:
            console.print(f"  [yellow]⚠️  统一审计桥注入失败: {e}[/yellow]")
        
        # 🎯 填充 CostTracker / 错误预算数据
        try:
            from maref.observability.metric_store import MetricStore
            from maref.recursive.cost_tracker import CostTracker
            _ms = MetricStore()
            _ct = CostTracker(metric_store=_ms)
            # 注入治理成本记录
            _ct.track(
                agent_id="trae-cn",
                action="governance_check", 
                tokens=50,
                cost=0.001,
                metadata={"source": "sidecar_bootstrap"}
            )
            console.print("  [green]✅ CostTracker 已初始化[/green]")
        except Exception:
            console.print("  [yellow]⚠️  CostTracker 初始化跳过[/yellow]")
        
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
        a2a_bridge = create_a2a_bridge()
        signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
        app.include_router(create_a2a_router(a2a_bridge, signing_key=signing_key))
        
        # 验证修复
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        gaas_count = sum(1 for r in routes if 'gaas' in r)
        console.print(f"  [green]GaaS 路由:[/green] {gaas_count} 个")
        
        # 检查关键端点
        key_endpoints = [
            ("/api/health", "健康检查"),
            ("/api/v1/gaas/govern", "GaaS 治理"),
            ("/api/v1/governance/state", "治理状态"),
        ]
        
        for endpoint, description in key_endpoints:
            found = any(endpoint in r for r in routes)
            status = "✅" if found else "❌"
            console.print(f"  {status} {description}: {endpoint}")
        
        # 启动服务器
        console.print("\n[dim]按 Ctrl+C 停止服务器[/dim]")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
        
    except ImportError as e:
        console.print(f"[red]导入失败: {e}[/red]")
        console.print("[red]请确保 MAREF 已正确安装[/red]")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[red]启动失败: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1) from None

@app.command()
def start(
    port: int = typer.Option(8000, "--port", "-p", help="Sidecar HTTP server port"),
    gui: bool = typer.Option(False, "--gui/--no-gui", help="Enable GUI endpoints"),
) -> None:
    """启动修复版 sidecar + 注册 MCP 到 opencode"""
    console.print("[bold green]MAREF Start — 修复版治理运行时[/bold green]")
    
    # 检查 opencode.json
    import json
    from pathlib import Path
    
    project_root = Path(__file__).resolve().parent.parent
    opencode_config = project_root / "opencode.json"
    
    if opencode_config.exists():
        console.print(f"  [green]MCP 配置:[/green] {opencode_config}")
        console.print("  [green]opencode[/green] 将在下次启动时发现 MAREF 工具")
    else:
        console.print("  [yellow]警告:[/yellow] opencode.json 未找到 — MCP 自动注册不可用")
    
    # 启动服务器
    serve(port=port, gui=gui)

def main():
    """主入口点"""
    app()

if __name__ == "__main__":
    main()