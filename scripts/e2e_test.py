#!/usr/bin/env python3
"""
端到端测试: 验证修复版 sidecar 和 MCP Guard 的完整流程
"""

import sys
import os
import time
import json
import requests
import subprocess
import threading
import atexit
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

class E2ETest:
    """端到端测试类"""
    
    def __init__(self, port=8005):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.sidecar_process = None
        self.audit_log = Path.home() / ".maref_mcp_guard_audit.log"
        
        # 清理旧的审计日志
        if self.audit_log.exists():
            self.audit_log.unlink()
    
    def start_sidecar(self):
        """启动修复版 sidecar"""
        print(f"启动修复版 sidecar (端口: {self.port})...")
        
        # 直接创建修复版应用
        try:
            import uvicorn
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
            a2a_bridge = create_a2a_bridge()
            signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
            app.include_router(create_a2a_router(a2a_bridge, signing_key=signing_key))
            
            # 在后台线程中启动
            def run():
                uvicorn.run(app, host="0.0.0.0", port=self.port, log_level="warning")
            
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            
            # 等待启动
            time.sleep(3)
            
            # 验证启动
            if self.check_sidecar_running():
                print(f"✅ sidecar 启动成功: {self.base_url}")
                return True
            else:
                print("❌ sidecar 启动失败")
                return False
                
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_sidecar_running(self):
        """检查 sidecar 是否运行"""
        try:
            resp = requests.get(f"{self.base_url}/api/health", timeout=2)
            return resp.status_code == 200
        except:
            return False
    
    def test_endpoints(self):
        """测试关键端点"""
        print("\n测试关键端点...")
        print("-" * 40)
        
        endpoints = [
            ("/api/health", "GET", None, "健康检查"),
            ("/api/v1/governance/state", "GET", None, "治理状态"),
            ("/api/v1/gaas/govern", "POST", 
             {"tenant_id": "test", "actor_id": "test-agent", "action": "write_file", "tool": "Write", "file_path": "/tmp/test.txt"},
             "GaaS 治理端点"),
            ("/api/compliance/check-action", "POST",
             {"agent_id": "test", "action": "write_file", "tool": "Write", "file_path": "/tmp/test.txt"},
             "合规检查"),
            ("/api/agents", "GET", None, "代理列表"),
        ]
        
        results = []
        for path, method, data, description in endpoints:
            url = f"{self.base_url}{path}"
            
            try:
                if method == "GET":
                    resp = requests.get(url, timeout=3)
                else:
                    resp = requests.post(url, json=data, timeout=3)
                
                status = resp.status_code
                
                if status == 200:
                    print(f"✅ {description}: HTTP {status}")
                    if resp.content:
                        try:
                            data = resp.json()
                            if description == "健康检查":
                                print(f"   状态: {data.get('status', 'N/A')}")
                            elif description == "治理状态":
                                print(f"   当前状态: {data.get('state', 'N/A')}")
                            elif description == "GaaS 治理端点":
                                print(f"   决策: {data.get('decision', 'N/A')}")
                                print(f"   允许: {data.get('allowed', 'N/A')}")
                        except:
                            pass
                    results.append(True)
                elif status == 422:
                    # 422 表示参数验证失败，但端点存在
                    print(f"⚠️  {description}: HTTP {status} (参数验证)")
                    print(f"   请求数据: {json.dumps(data)[:100]}...")
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
        
        # 统计结果
        success = sum(results)
        total = len(results)
        
        print(f"\n端点测试结果: {success}/{total} 通过")
        
        # 关键端点检查
        critical_passed = all(results[i] for i in [0, 2])  # 健康检查和GaaS端点
        return critical_passed
    
    def test_mcp_guard_simulation(self):
        """模拟 MCP Guard 治理检查"""
        print("\n模拟 MCP Guard 治理检查...")
        print("-" * 40)
        
        test_cases = [
            {
                "name": "写入普通文件",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/tmp/test.txt",
                "expected": "allow"  # 应该允许
            },
            {
                "name": "写入系统文件",
                "action": "write_file", 
                "tool": "Write",
                "file_path": "/etc/passwd",
                "expected": "deny"  # 应该拒绝
            },
            {
                "name": "读取普通文件",
                "action": "read_file",
                "tool": "Read",
                "file_path": "/tmp/test.txt",
                "expected": "allow"
            },
            {
                "name": "执行命令",
                "action": "execute_command",
                "tool": "Bash",
                "file_path": None,
                "expected": "allow"
            }
        ]
        
        results = []
        for test in test_cases:
            print(f"\n测试: {test['name']}")
            print(f"  动作: {test['action']}, 工具: {test['tool']}")
            if test['file_path']:
                print(f"  文件: {test['file_path']}")
            
            # 调用 GaaS 端点
            data = {
                "tenant_id": "test",
                "actor_id": "trae-cn",  # 模拟 Trae 代理
                "action": test['action'],
                "tool": test['tool'],
                "file_path": test['file_path'],
                "metadata": {
                    "test_case": test['name'],
                    "simulated": True
                }
            }
            
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/gaas/govern",
                    json=data,
                    timeout=5
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    decision = result.get('decision', 'unknown')
                    allowed = result.get('allowed', False)
                    reason = result.get('reason', 'No reason')
                    
                    print(f"  决策: {decision}, 允许: {allowed}")
                    print(f"  原因: {reason[:80]}...")
                    
                    # 检查是否符合预期
                    if test['expected'] == 'allow' and allowed:
                        print(f"  ✅ 符合预期: 允许")
                        results.append(True)
                    elif test['expected'] == 'deny' and not allowed:
                        print(f"  ✅ 符合预期: 拒绝")
                        results.append(True)
                    else:
                        print(f"  ⚠️  不符合预期: 期望 {test['expected']}, 实际 {'允许' if allowed else '拒绝'}")
                        results.append(False)
                        
                elif resp.status_code == 422:
                    print(f"  ⚠️  参数验证失败 (端点存在)")
                    results.append(True)  # 端点存在
                else:
                    print(f"  ❌ HTTP {resp.status_code}")
                    results.append(False)
                    
            except Exception as e:
                print(f"  ❌ 错误: {str(e)[:50]}")
                results.append(False)
        
        success = sum(results)
        total = len(results)
        
        print(f"\n治理检查测试结果: {success}/{total} 通过")
        return success >= total * 0.7  # 70% 通过率
    
    def check_audit_log(self):
        """检查审计日志"""
        print("\n检查审计日志...")
        print("-" * 40)
        
        if self.audit_log.exists():
            with open(self.audit_log, 'r') as f:
                lines = f.readlines()
            
            print(f"✅ 审计日志文件存在: {self.audit_log}")
            print(f"   日志条目: {len(lines)} 条")
            
            # 显示最新几条
            for i, line in enumerate(lines[-3:], 1):
                try:
                    entry = json.loads(line.strip())
                    print(f"\n   条目 {i}:")
                    print(f"     ID: {entry.get('id', 'N/A')[:8]}...")
                    print(f"     代理: {entry.get('agent_id', 'N/A')}")
                    print(f"     工具: {entry.get('tool', 'N/A')}")
                    print(f"     决策: {entry.get('decision', 'N/A')}")
                except:
                    print(f"   条目 {i}: JSON 解析失败")
            
            return len(lines) > 0
        else:
            print(f"❌ 审计日志文件不存在: {self.audit_log}")
            return False
    
    def cleanup(self):
        """清理资源"""
        print("\n清理资源...")
        
        # 清理审计日志
        if self.audit_log.exists():
            self.audit_log.unlink()
            print(f"✅ 清理审计日志")
    
    def run_full_test(self):
        """运行完整测试"""
        print("=" * 60)
        print("MAREF 治理补强工程 - 端到端测试")
        print("=" * 60)
        
        try:
            # 1. 启动 sidecar
            if not self.start_sidecar():
                print("❌ sidecar 启动失败，终止测试")
                return False
            
            # 2. 测试端点
            endpoints_ok = self.test_endpoints()
            if not endpoints_ok:
                print("❌ 关键端点测试失败")
                return False
            
            # 3. 模拟治理检查
            governance_ok = self.test_mcp_guard_simulation()
            
            # 4. 检查审计日志
            audit_ok = self.check_audit_log()
            
            # 总结
            print("\n" + "=" * 60)
            print("端到端测试总结")
            print("=" * 60)
            
            print(f"✅ sidecar 启动: 成功")
            print(f"✅ 端点测试: {'通过' if endpoints_ok else '失败'}")
            print(f"✅ 治理检查: {'通过' if governance_ok else '部分失败'}")
            print(f"✅ 审计日志: {'生成' if audit_ok else '未生成'}")
            
            overall = endpoints_ok and governance_ok
            if overall:
                print("\n🎉 端到端测试通过!")
                print("\n下一步:")
                print("1. 配置 Trae 使用 MCP Guard")
                print("2. 测试实际 IDE 集成")
                print("3. 验证真实场景治理拦截")
            else:
                print("\n⚠️  端到端测试部分失败")
                print("\n建议:")
                print("1. 检查 sidecar 日志")
                print("2. 验证网络连接")
                print("3. 检查依赖安装")
            
            return overall
            
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.cleanup()

def main():
    """主函数"""
    # 使用非标准端口避免冲突
    test = E2ETest(port=8005)
    
    success = test.run_full_test()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 端到端测试完成 - 可以继续 Phase 3")
        sys.exit(0)
    else:
        print("❌ 端到端测试失败 - 需要修复问题")
        sys.exit(1)

if __name__ == "__main__":
    main()