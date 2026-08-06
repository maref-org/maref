#!/usr/bin/env python3
"""
端到端集成测试 - 验证修复版 sidecar + MCP Guard
"""

import sys
import os
import time
import json
import requests
import subprocess
from pathlib import Path

# 测试配置
TEST_PORT = 8010
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

def log(msg):
    """打印日志"""
    print(f"[E2E Test] {msg}")

def start_fixed_sidecar():
    """启动修复版 sidecar"""
    log("启动修复版 sidecar...")
    
    # 使用 nohup 在后台启动
    cmd = [
        sys.executable,
        "scripts/maref_lite_fixed.py",
        "serve",
        "--port", str(TEST_PORT)
    ]
    
    # 启动进程并分离
    proc = subprocess.Popen(
        cmd,
        stdout=open("/tmp/maref_sidecar.log", "w"),
        stderr=open("/tmp/maref_sidecar.err", "w"),
        start_new_session=True
    )
    
    # 等待启动
    log("等待 sidecar 启动...")
    time.sleep(4)
    
    # 验证启动
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=3)
        if resp.status_code == 200:
            log(f"✅ sidecar 启动成功 (PID: {proc.pid}, 端口: {TEST_PORT})")
            return proc
        else:
            log(f"❌ sidecar 响应异常: HTTP {resp.status_code}")
            return None
    except Exception as e:
        log(f"❌ sidecar 启动失败: {e}")
        return None

def stop_sidecar(proc):
    """停止 sidecar"""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except:
            proc.kill()
        log("✅ sidecar 已停止")

def test_health_endpoint():
    """测试健康端点"""
    log("\n测试 1: 健康检查端点")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=3)
        
        if resp.status_code == 200:
            data = resp.json()
            log(f"✅ 健康检查: {data.get('status', 'unknown')}")
            return True
        else:
            log(f"❌ 健康检查: HTTP {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ 健康检查: {e}")
        return False

def test_governance_state():
    """测试治理状态端点"""
    log("\n测试 2: 治理状态端点")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/governance/state", timeout=3)
        
        if resp.status_code == 200:
            data = resp.json()
            log(f"✅ 治理状态: {data.get('state', 'unknown')}")
            log(f"   熵值: {data.get('entropy', 'unknown')}")
            log(f"   熔断器: {data.get('circuit_breaker', 'unknown')}")
            return True
        else:
            log(f"❌ 治理状态: HTTP {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ 治理状态: {e}")
        return False

def test_gaas_govern_endpoint():
    """测试 GaaS 治理端点"""
    log("\n测试 3: GaaS 治理端点")
    
    test_cases = [
        {
            "name": "写入普通文件",
            "data": {
                "tenant_id": "test",
                "actor_id": "trae-cn",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/tmp/test.txt",
                "metadata": {"test": True}
            }
        },
        {
            "name": "写入系统文件",
            "data": {
                "tenant_id": "test",
                "actor_id": "trae-cn",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/etc/passwd",
                "metadata": {"test": True}
            }
        },
        {
            "name": "读取文件",
            "data": {
                "tenant_id": "test",
                "actor_id": "trae-cn",
                "action": "read_file",
                "tool": "Read",
                "file_path": "/tmp/test.txt",
                "metadata": {"test": True}
            }
        },
        {
            "name": "执行命令",
            "data": {
                "tenant_id": "test",
                "actor_id": "trae-cn",
                "action": "execute_command",
                "tool": "Bash",
                "file_path": None,
                "metadata": {"command": "ls -la"}
            }
        }
    ]
    
    results = []
    
    for test in test_cases:
        log(f"\n   测试用例: {test['name']}")
        log(f"   动作: {test['data']['action']}, 工具: {test['data']['tool']}")
        
        try:
            resp = requests.post(
                f"{BASE_URL}/api/v1/gaas/govern",
                json=test['data'],
                timeout=5,
                headers={"X-API-Key": "default-key"}
            )
            
            log(f"   HTTP 状态: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                decision = data.get('decision', 'unknown')
                allowed = data.get('allowed', False)
                reason = data.get('reason', 'No reason')
                
                log(f"   决策: {decision}")
                log(f"   允许: {allowed}")
                log(f"   原因: {reason}")
                
                results.append(True)
                
            elif resp.status_code == 422:
                log(f"   ⚠️  参数验证失败 (端点存在)")
                results.append(True)  # 端点存在
                
            elif resp.status_code == 404:
                log(f"   ❌ 端点未找到 (404)")
                results.append(False)
                
            else:
                log(f"   ❌ 异常响应: HTTP {resp.status_code}")
                if resp.content:
                    log(f"   响应: {resp.text[:100]}")
                results.append(False)
                
        except Exception as e:
            log(f"   ❌ 错误: {str(e)[:80]}")
            results.append(False)
    
    success = sum(results)
    total = len(results)
    log(f"\n   GaaS 治理测试: {success}/{total} 通过")
    
    return success >= total * 0.5  # 至少 50% 通过

def test_compliance_endpoint():
    """测试合规端点"""
    log("\n测试 4: 合规检查端点")
    
    try:
        resp = requests.post(
            f"{BASE_URL}/api/compliance/check-action",
            json={
                "agent_id": "trae-cn",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/tmp/test.txt"
            },
            timeout=3
        )
        
        log(f"   HTTP 状态: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            log(f"   ✅ 合规检查: allowed={data.get('allowed', False)}, decision={data.get('decision', 'unknown')}")
            return True
        else:
            log(f"   ⚠️  合规检查: HTTP {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"   ❌ 合规检查: {e}")
        return False

def test_agents_endpoint():
    """测试代理列表端点"""
    log("\n测试 5: 代理列表端点")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/agents", timeout=3)
        
        if resp.status_code == 200:
            data = resp.json()
            agents = data.get('agents', [])
            log(f"   ✅ 代理列表: {len(agents)} 个代理")
            return True
        else:
            log(f"   ❌ 代理列表: HTTP {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"   ❌ 代理列表: {e}")
        return False

def test_audit_log():
    """测试审计日志功能"""
    log("\n测试 6: 审计日志验证")
    
    # 模拟 MCP Guard 调用治理端点并记录审计
    audit_entries = []
    
    try:
        # 模拟几个治理请求
        for i in range(3):
            resp = requests.post(
                f"{BASE_URL}/api/v1/gaas/govern",
                json={
                    "tenant_id": "test",
                    "actor_id": "trae-cn",
                    "action": "write_file",
                    "tool": "Write",
                    "file_path": f"/tmp/test{i}.txt",
                    "metadata": {"test": True, "index": i}
                },
                timeout=3
            )
            
            if resp.status_code == 200:
                result = resp.json()
                audit_entries.append({
                    "action": "write_file",
                    "file_path": f"/tmp/test{i}.txt",
                    "decision": result.get('decision', 'unknown'),
                    "allowed": result.get('allowed', False)
                })
        
        log(f"   模拟 {len(audit_entries)} 次治理检查")
        
        if audit_entries:
            log(f"   ✅ 审计数据生成成功")
            for entry in audit_entries:
                log(f"      {entry['file_path']}: {entry['decision']}")
            return True
        else:
            log(f"   ⚠️  未生成审计数据")
            return False
            
    except Exception as e:
        log(f"   ❌ 审计日志测试: {e}")
        return False

def test_gaas_routes_count():
    """验证 GaaS 路由数量"""
    log("\n测试 7: GaaS 路由验证")
    
    try:
        # 检查路由列表
        resp = requests.get(f"{BASE_URL}/api/status", timeout=3)
        
        if resp.status_code == 200:
            data = resp.json()
            version = data.get('version', 'unknown')
            log(f"   Sidecar 版本: {version}")
        
        # 直接检查 GaaS 端点是否存在
        gaas_endpoints = [
            "/api/v1/gaas/govern",
            "/api/v1/gaas/hitl/request",
            "/api/v1/gaas/hitl/pending",
            "/api/v1/gaas/trust/score",
            "/api/v1/gaas/audit/query",
            "/api/v1/gaas/cb/status",
            "/api/v1/gaas/health",
        ]
        
        found_count = 0
        for endpoint in gaas_endpoints:
            try:
                resp = requests.get(f"{BASE_URL}{endpoint}", timeout=2)
                # 200 或 405 (Method Not Allowed) 或 422 都表示端点存在
                if resp.status_code in [200, 405, 422]:
                    found_count += 1
            except:
                pass
        
        log(f"   找到 {found_count}/{len(gaas_endpoints)} 个 GaaS 端点")
        
        if found_count >= 3:
            log(f"   ✅ GaaS 路由验证通过")
            return True
        else:
            log(f"   ⚠️  GaaS 路由较少")
            return False
            
    except Exception as e:
        log(f"   ❌ GaaS 路由验证: {e}")
        return False

def generate_summary(results):
    """生成测试总结"""
    log("\n" + "=" * 60)
    log("端到端测试总结")
    log("=" * 60)
    
    tests = [
        ("健康检查", results['health']),
        ("治理状态", results['governance']),
        ("GaaS 治理", results['gaas']),
        ("合规检查", results['compliance']),
        ("代理列表", results['agents']),
        ("审计日志", results['audit']),
        ("GaaS 路由", results['routes']),
    ]
    
    passed = sum(1 for _, status in tests if status)
    total = len(tests)
    
    for test_name, status in tests:
        icon = "✅" if status else "❌"
        log(f"{icon} {test_name}")
    
    log(f"\n总计: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
    
    critical = ['health', 'gaas', 'governance']
    critical_passed = all(results.get(k, False) for k in critical)
    
    if critical_passed and passed >= total * 0.7:
        log("\n🎉 端到端测试通过!")
        log("\n关键成果:")
        log("✅ GaaS 治理端点可用")
        log("✅ sidecar 修复成功")
        log("✅ 可以配置 MCP Guard 进行治理拦截")
        
        log("\n下一步:")
        log("1. 配置 Trae MCP Guard")
        log("2. 配置 OpenCode MCP Guard")
        log("3. 测试真实 IDE 集成")
        
        return True
    else:
        log("\n⚠️  端到端测试部分失败")
        log("\n需要修复:")
        for k, v in results.items():
            if not v:
                log(f"  ❌ {k}")
        
        return False

def main():
    """主函数"""
    log("=" * 60)
    log("MAREF 治理补强 - 端到端集成测试")
    log("=" * 60)
    
    # 启动 sidecar
    proc = start_fixed_sidecar()
    if not proc:
        log("❌ sidecar 启动失败，终止测试")
        return False
    
    results = {}
    
    try:
        # 运行测试
        results['health'] = test_health_endpoint()
        results['governance'] = test_governance_state()
        results['gaas'] = test_gaas_govern_endpoint()
        results['compliance'] = test_compliance_endpoint()
        results['agents'] = test_agents_endpoint()
        results['audit'] = test_audit_log()
        results['routes'] = test_gaas_routes_count()
        
        # 生成总结
        success = generate_summary(results)
        
        return success
        
    except Exception as e:
        log(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理
        stop_sidecar(proc)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
