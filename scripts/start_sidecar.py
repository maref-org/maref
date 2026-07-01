#!/usr/bin/env python3
"""
启动 MAREF sidecar 服务器用于开发和测试。

使用方法:
1. 直接运行: python3 scripts/start_sidecar.py
2. 后台运行: python3 scripts/start_sidecar.py --daemon
3. 指定端口: python3 scripts/start_sidecar.py --port 9000
"""

import argparse
import sys
import os
import time
import subprocess
import signal
import atexit

def check_dependencies():
    """检查必要的依赖"""
    try:
        import uvicorn
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.obs_bridge import ObsBridge
        from sidecar.server import create_app
        return True
    except ImportError as e:
        print(f"依赖导入失败: {e}")
        print("请确保 MAREF 已正确安装:")
        print("  pip install -e . --break-system-packages")
        return False

def start_sidecar(port=8000, daemon=False, telemetry=False):
    """启动 sidecar 服务器"""
    try:
        import uvicorn
        from maref.obs import MarefObsClient
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.obs_bridge import ObsBridge
        from sidecar.server import create_app
        
        print(f"启动 MAREF sidecar 服务器 (端口: {port})")
        print("=" * 50)
        
        # 创建依赖
        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        obs_bridge = ObsBridge(client=MarefObsClient.get_default()) if telemetry else None
        
        # 创建 FastAPI 应用
        app = create_app(collector, monitor, obs_bridge=obs_bridge)
        
        print(f"✅ 服务器已初始化")
        print(f"📊 健康检查: http://127.0.0.1:{port}/api/health")
        print(f"🔧 治理状态: http://127.0.0.1:{port}/api/v1/governance/state")
        print(f"⚖️  GaaS 端点: http://127.0.0.1:{port}/api/v1/gaas/govern")
        print(f"📋 代理列表: http://127.0.0.1:{port}/api/agents")
        print("=" * 50)
        print("按 Ctrl+C 停止服务器")
        
        if daemon:
            print("🔄 以守护进程模式运行...")
            # 在后台运行
            import threading
            def run():
                uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
            
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            return thread
        else:
            # 前台运行
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
            
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_sidecar_running(port=8000):
    """检查 sidecar 是否在运行"""
    import requests
    try:
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def stop_sidecar(pid_file="/tmp/maref_sidecar.pid"):
    """停止 sidecar 服务器"""
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"已停止 sidecar 进程 {pid}")
            os.remove(pid_file)
        except ProcessLookupError:
            print("进程不存在，清理 PID 文件")
            os.remove(pid_file)
        except Exception as e:
            print(f"停止失败: {e}")
    else:
        print("未找到 PID 文件")

def main():
    parser = argparse.ArgumentParser(description="MAREF sidecar 服务器启动器")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口 (默认: 8000)")
    parser.add_argument("--daemon", action="store_true", help="以守护进程模式运行")
    parser.add_argument("--stop", action="store_true", help="停止正在运行的服务器")
    parser.add_argument("--status", action="store_true", help="检查服务器状态")
    parser.add_argument("--telemetry", action="store_true", help="启用遥测桥接")
    
    args = parser.parse_args()
    
    if args.stop:
        stop_sidecar()
        return
    
    if args.status:
        if check_sidecar_running(args.port):
            print(f"✅ sidecar 正在端口 {args.port} 运行")
            try:
                import requests
                resp = requests.get(f"http://127.0.0.1:{args.port}/api/health", timeout=2)
                print(f"健康状态: {resp.json()}")
            except Exception as e:
                print(f"获取状态失败: {e}")
        else:
            print(f"❌ sidecar 未在端口 {args.port} 运行")
        return
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 检查是否已在运行
    if check_sidecar_running(args.port):
        print(f"⚠️  sidecar 已在端口 {args.port} 运行")
        print("使用 --stop 停止现有实例，或使用不同端口")
        sys.exit(1)
    
    # 启动服务器
    start_sidecar(port=args.port, daemon=args.daemon, telemetry=args.telemetry)

if __name__ == "__main__":
    main()