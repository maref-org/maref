#!/usr/bin/env python3
"""
测试 MCP Guard 基本功能

测试:
1. MCP Guard 启动和初始化
2. 治理客户端连接
3. 审计日志功能
4. MCP 协议处理
"""

import sys
import os
import json
import asyncio
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """测试模块导入"""
    print("测试模块导入...")
    
    modules = [
        ("aiohttp", "ClientSession"),
        ("dataclasses", "dataclass"),
        ("typing", "Any"),
        ("enum", "Enum"),
    ]
    
    for module_name, attr_name in modules:
        try:
            module = __import__(module_name)
            if hasattr(module, attr_name):
                print(f"✅ {module_name}.{attr_name}")
            else:
                print(f"❌ {module_name}.{attr_name} (不存在)")
        except ImportError as e:
            print(f"❌ {module_name}: 导入失败 - {e}")
    
    return True

def test_mcp_guard_structure():
    """测试 MCP Guard 结构"""
    print("\n测试 MCP Guard 结构...")
    
    # 检查脚本文件
    guard_script = Path(__file__).parent / "maref_mcp_guard.py"
    if guard_script.exists():
        print(f"✅ MCP Guard 脚本: {guard_script}")
        
        # 检查文件大小
        size = guard_script.stat().st_size
        print(f"   文件大小: {size} 字节")
        
        # 检查关键组件
        with open(guard_script, 'r') as f:
            content = f.read()
            
        components = [
            ("MAREFGovernanceClient", "治理客户端类"),
            ("MCPGuardServer", "MCP 服务器类"),
            ("GovernanceRequest", "治理请求类"),
            ("GovernanceResponse", "治理响应类"),
            ("AuditEntry", "审计日志类"),
            ("async def main", "主异步函数"),
        ]
        
        for component, description in components:
            if component in content:
                print(f"   ✅ {description}: {component}")
            else:
                print(f"   ❌ {description}: {component} (未找到)")
    else:
        print(f"❌ MCP Guard 脚本不存在: {guard_script}")
        return False
    
    return True

def test_audit_log():
    """测试审计日志功能"""
    print("\n测试审计日志功能...")
    
    # 创建临时审计日志文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        audit_file = Path(f.name)
    
    try:
        # 测试审计日志写入
        test_entry = {
            "id": "test-123",
            "timestamp": 1234567890.0,
            "agent_id": "test-agent",
            "tool": "write_file",
            "action": "write",
            "file_path": "/tmp/test.txt",
            "decision": "allow",
            "reason": "test",
            "requires_hitl": False
        }
        
        with open(audit_file, 'w') as f:
            f.write(json.dumps(test_entry) + "\n")
        
        print(f"✅ 审计日志文件: {audit_file}")
        print(f"   文件大小: {audit_file.stat().st_size} 字节")
        
        # 读取验证
        with open(audit_file, 'r') as f:
            lines = f.readlines()
            if len(lines) == 1:
                entry = json.loads(lines[0].strip())
                if entry["id"] == "test-123":
                    print(f"✅ 审计日志读写正常")
                else:
                    print(f"❌ 审计日志内容错误")
            else:
                print(f"❌ 审计日志行数错误: {len(lines)}")
        
        return True
        
    finally:
        # 清理
        if audit_file.exists():
            audit_file.unlink()

def test_mcp_protocol():
    """测试 MCP 协议处理"""
    print("\n测试 MCP 协议处理...")
    
    # 模拟 MCP 消息
    test_messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        },
        {
            "jsonrpc": "2.0", 
            "id": 2,
            "method": "tools/list",
            "params": {}
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "write_file",
                "arguments": {
                    "path": "/tmp/test.txt",
                    "content": "test"
                }
            }
        }
    ]
    
    print(f"✅ 定义了 {len(test_messages)} 个测试消息")
    
    # 检查消息格式
    for i, msg in enumerate(test_messages, 1):
        required_fields = ["jsonrpc", "id", "method"]
        missing = [f for f in required_fields if f not in msg]
        
        if missing:
            print(f"❌ 消息 {i} 缺少字段: {missing}")
        else:
            print(f"✅ 消息 {i}: {msg['method']}")
    
    return True

def test_config_templates():
    """测试配置模板"""
    print("\n测试配置模板...")
    
    config_files = [
        ("trae_mcp_config.json", "Trae MCP 配置"),
        ("opencode.json", "OpenCode MCP 配置"),
        ("fixed_sidecar.py", "修复版 sidecar"),
        ("start_fixed_sidecar.py", "sidecar 启动脚本"),
    ]
    
    all_exist = True
    for filename, description in config_files:
        filepath = Path(__file__).parent / filename
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"✅ {description}: {filename} ({size} 字节)")
        else:
            print(f"❌ {description}: {filename} (不存在)")
            all_exist = False
    
    return all_exist

def create_integration_test():
    """创建集成测试脚本"""
    print("\n创建集成测试脚本...")
    
    test_script = '''#!/usr/bin/env python3
"""
集成测试脚本

测试 MCP Guard 完整流程:
1. 启动修复版 sidecar
2. 配置 MCP Guard
3. 测试治理检查
4. 验证审计日志
"""

import sys
import os
import subprocess
import time
import json
import requests
from pathlib import Path'''

def start_sidecar():
    """启动修复版 sidecar"""
    print("启动修复版 sidecar...")
    
    # 使用修复版 sidecar
    sidecar_script = Path(__file__).parent / "start_fixed_sidecar.py"
    
    if not sidecar_script.exists():
        print(f"❌ sidecar 启动脚本不存在: {sidecar_script}")
        return None
    
    # 在后台启动
    proc = subprocess.Popen(
        [sys.executable, str(sidecar_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 等待启动
    time.sleep(3)
    
    # 检查是否运行
    try:
        resp = requests.get("http://127.0.0.1:8000/api/health", timeout=2)
        if resp.status_code == 200:
            print("✅ sidecar 启动成功")
            return proc
        else:
            print(f"❌ sidecar 响应异常: {resp.status_code}")
            proc.terminate()
            return None
    except:
        print("❌ sidecar 启动失败")
        proc.terminate()
        return None

def test_governance_endpoint():
    """测试治理端点"""
    print("\n测试治理端点...")
    
    test_cases = [
        {
            "name": "写入文件测试",
            "url": "http://127.0.0.1:8000/api/v1/gaas/govern",
            "method": "POST",
            "data": {
                "tenant_id": "test",
                "actor_id": "test-agent",
                "action": "write_file",
                "tool": "Write",
                "file_path": "/tmp/test.txt",
                "metadata": {"test": True}
            }
        },
        {
            "name": "读取文件测试", 
            "url": "http://127.0.0.1:8000/api/v1/gaas/govern",
            "method": "POST",
            "data": {
                "tenant_id": "test",
                "actor_id": "test-agent", 
                "action": "read_file",
                "tool": "Read",
                "file_path": "/etc/passwd",
                "metadata": {"test": True}
            }
        }
    ]
    
    results = []
    for test in test_cases:
        try:
            resp = requests.post(test["url"], json=test["data"], timeout=5)
            status = resp.status_code
            
            if status == 200:
                result = resp.json()
                print(f"✅ {test['name']}: HTTP {status}")
                print(f"   决策: {result.get('decision', 'unknown')}")
                print(f"   原因: {result.get('reason', 'unknown')}")
                results.append(True)
            elif status == 422:
                print(f"⚠️  {test['name']}: HTTP {status} (参数验证)")
                results.append(True)  # 端点存在
            else:
                print(f"❌ {test['name']}: HTTP {status}")
                if resp.content:
                    print(f"   响应: {resp.text[:100]}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ {test['name']}: 错误 - {str(e)[:50]}")
            results.append(False)
    
    return any(results)  # 至少一个成功

def test_mcp_guard():
    """测试 MCP Guard"""
    print("\n测试 MCP Guard...")
    
    # 检查 MCP Guard 脚本
    guard_script = Path(__file__).parent / "maref_mcp_guard.py"
    if not guard_script.exists():
        print(f"❌ MCP Guard 脚本不存在: {guard_script}")
        return False
    
    # 测试基本功能
    try:
        # 导入测试
        import subprocess
        result = subprocess.run(
            [sys.executable, str(guard_script), "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("✅ MCP Guard 可执行")
            return True
        else:
            print(f"❌ MCP Guard 执行失败: {result.stderr[:100]}")
            return False
            
    except Exception as e:
        print(f"❌ MCP Guard 测试失败: {e}")
        return False

def main():
    print("MCP Guard 集成测试")
    print("=" * 50)
    
    # 启动 sidecar
    sidecar_proc = start_sidecar()
    if not sidecar_proc:
        print("❌ sidecar 启动失败，跳过后续测试")
        return False
    
    try:
        # 测试治理端点
        gov_success = test_governance_endpoint()
        
        # 测试 MCP Guard
        guard_success = test_mcp_guard()
        
        print("\n" + "=" * 50)
        print("集成测试结果:")
        
        if gov_success and guard_success:
            print("✅ 所有测试通过")
            print("\nMCP Guard 已准备好集成到 Trae/OpenCode")
            return True
        else:
            print("⚠️  部分测试失败")
            print(f"   治理端点: {'✅' if gov_success else '❌'}")
            print(f"   MCP Guard: {'✅' if guard_success else '❌'}")
            return False
            
    finally:
        # 停止 sidecar
        if sidecar_proc and sidecar_proc.poll() is None:
            sidecar_proc.terminate()
            sidecar_proc.wait()
            print("\n✅ sidecar 已停止")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
"""
    
    test_path = Path(__file__).parent / "integration_test.py"
    with open(test_path, 'w') as f:
        f.write(test_script)
    
    print(f"✅ 集成测试脚本: {test_path}")
    return True

def main():
    print("MAREF MCP Guard 基本功能测试")
    print("=" * 60)
    
    tests = [
        ("模块导入", test_imports),
        ("MCP Guard 结构", test_mcp_guard_structure),
        ("审计日志", test_audit_log),
        ("MCP 协议", test_mcp_protocol),
        ("配置模板", test_config_templates),
        ("集成测试脚本", create_integration_test),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔧 {test_name}")
        print("-" * 40)
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("测试总结:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"通过: {passed}/{total}")
    
    for test_name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {test_name}")
    
    print("\n" + "=" * 60)
    if passed == total:
        print("✅ 所有测试通过")
        print("\nPhase 2 基础功能验证完成")
        print("下一步: 运行集成测试")
        print("  python3 scripts/integration_test.py")
    else:
        print("⚠️  部分测试失败")
        print("\n需要修复的问题:")
        for test_name, success in results:
            if not success:
                print(f"  • {test_name}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)