"""
Protocol Bridge 测试
"""

from __future__ import annotations

import pytest

from maref.protocols.protocol_bridge import (
    A2AMessage,
    A2ATask,
    BridgeDirection,
    MCPMessage,
    MCPResponse,
    ProtocolBridge,
    ProtocolType,
    SecureProtocolBridge,
    create_protocol_bridge,
    create_secure_protocol_bridge,
)


class TestMCPMessage:
    """测试 MCP 消息"""
    
    def test_create_message(self) -> None:
        """测试创建消息"""
        msg = MCPMessage(
            message_id="msg-1",
            method="tools/call",
            params={"name": "test_tool", "arguments": {}},
        )
        
        assert msg.message_id == "msg-1"
        assert msg.method == "tools/call"
    
    def test_to_dict(self) -> None:
        """测试字典转换"""
        msg = MCPMessage(
            message_id="msg-1",
            method="tools/call",
            params={"name": "test"},
        )
        
        data = msg.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "msg-1"
        assert data["method"] == "tools/call"
    
    def test_compute_hash(self) -> None:
        """测试哈希计算"""
        msg = MCPMessage(
            message_id="msg-1",
            method="tools/call",
            params={"name": "test"},
        )
        
        hash1 = msg.compute_hash()
        hash2 = msg.compute_hash()
        
        assert hash1 == hash2
        assert len(hash1) == 64


class TestA2ATask:
    """测试 A2A 任务"""
    
    def test_create_task(self) -> None:
        """测试创建任务"""
        task = A2ATask(
            task_id="task-1",
            agent_id="agent-a",
            action="execute",
            input_data={"cmd": "test"},
        )
        
        assert task.task_id == "task-1"
        assert task.agent_id == "agent-a"
        assert task.status == "pending"
    
    def test_to_dict(self) -> None:
        """测试字典转换"""
        task = A2ATask(
            task_id="task-1",
            agent_id="agent-a",
            action="execute",
            input_data={},
        )
        
        data = task.to_dict()
        assert data["task_id"] == "task-1"
        assert data["status"] == "pending"


class TestProtocolBridge:
    """测试协议桥接器"""
    
    def test_create_bridge(self) -> None:
        """测试创建桥接器"""
        bridge = create_protocol_bridge()
        assert isinstance(bridge, ProtocolBridge)
    
    def test_convert_mcp_to_a2a(self) -> None:
        """测试 MCP 到 A2A 转换"""
        bridge = create_protocol_bridge()
        
        mcp_msg = MCPMessage(
            message_id="msg-1",
            method="tools/call",
            params={"name": "calculator", "arguments": {"a": 1, "b": 2}},
        )
        
        task = bridge.convert_mcp_to_a2a(mcp_msg, "agent-math")
        
        assert task.agent_id == "agent-math"
        assert task.action == "execute_task"
        assert task.input_data["original_method"] == "tools/call"
    
    def test_convert_a2a_to_mcp_success(self) -> None:
        """测试 A2A 到 MCP 成功转换"""
        bridge = create_protocol_bridge()
        
        # 先创建一个 MCP 消息以建立映射
        mcp_msg = MCPMessage(
            message_id="msg-1",
            method="tools/call",
            params={},
        )
        task = bridge.convert_mcp_to_a2a(mcp_msg, "agent-1")
        
        # 完成任务
        task.status = "completed"
        task.output_data = {"result": 42}
        
        response = bridge.convert_a2a_to_mcp(task)
        
        assert response.message_id == "msg-1"
        assert response.is_error == False
        assert response.result is not None
    
    def test_convert_a2a_to_mcp_failure(self) -> None:
        """测试 A2A 到 MCP 失败转换"""
        bridge = create_protocol_bridge()
        
        mcp_msg = MCPMessage(
            message_id="msg-2",
            method="tools/call",
            params={},
        )
        task = bridge.convert_mcp_to_a2a(mcp_msg, "agent-1")
        
        task.status = "failed"
        task.output_data = {"error": "division by zero"}
        
        response = bridge.convert_a2a_to_mcp(task)
        
        assert response.is_error == True
        assert response.error is not None
        assert response.error["code"] == -32000
    
    def test_method_mapping(self) -> None:
        """测试方法映射"""
        bridge = create_protocol_bridge()
        
        # MCP -> A2A
        msg1 = MCPMessage(message_id="1", method="tools/call", params={})
        task1 = bridge.convert_mcp_to_a2a(msg1, "agent-1")
        assert task1.action == "execute_task"
        
        msg2 = MCPMessage(message_id="2", method="resources/read", params={})
        task2 = bridge.convert_mcp_to_a2a(msg2, "agent-1")
        assert task2.action == "fetch_artifact"
    
    def test_create_mcp_tool_request(self) -> None:
        """测试创建 MCP 工具请求"""
        bridge = create_protocol_bridge()
        
        msg = bridge.create_mcp_tool_request(
            tool_name="calculator",
            arguments={"a": 1, "b": 2},
        )
        
        assert msg.method == "tools/call"
        assert msg.params["name"] == "calculator"
        assert msg.params["arguments"]["a"] == 1
    
    def test_create_a2a_task_request(self) -> None:
        """测试创建 A2A 任务请求"""
        bridge = create_protocol_bridge()
        
        task = bridge.create_a2a_task_request(
            agent_id="agent-1",
            action="compute",
            input_data={"expr": "1+2"},
        )
        
        assert task.agent_id == "agent-1"
        assert task.action == "compute"
        assert task.input_data["expr"] == "1+2"
    
    def test_error_mapping_mcp_to_a2a(self) -> None:
        """测试 MCP 到 A2A 错误映射"""
        bridge = create_protocol_bridge()
        
        mcp_error = {"code": -32601, "message": "Method not found"}
        a2a_error = bridge.map_error(ProtocolType.MCP, mcp_error)
        
        assert a2a_error["type"] == "method_not_found"
    
    def test_error_mapping_a2a_to_mcp(self) -> None:
        """测试 A2A 到 MCP 错误映射"""
        bridge = create_protocol_bridge()
        
        a2a_error = {"type": "timeout"}
        mcp_error = bridge.map_error(ProtocolType.A2A, a2a_error)
        
        assert mcp_error["code"] == -32001
    
    def test_metrics_tracking(self) -> None:
        """测试指标追踪"""
        bridge = create_protocol_bridge()
        
        mcp_msg = MCPMessage(message_id="1", method="tools/call", params={})
        bridge.convert_mcp_to_a2a(mcp_msg, "agent-1")
        
        metrics = bridge.get_metrics()
        
        assert metrics["total_converted"] == 1
        assert metrics["mcp_to_a2a"] == 1
    
    def test_bridge_session(self) -> None:
        """测试桥接会话"""
        bridge = create_protocol_bridge()
        
        session_id = bridge.generate_bridge_session("agent-a", "agent-b")
        
        assert session_id.startswith("bridge-")
        assert session_id in bridge._session_store


class TestSecureProtocolBridge:
    """测试安全协议桥接器"""
    
    def test_create_secure_bridge(self) -> None:
        """测试创建安全桥接器"""
        bridge = create_secure_protocol_bridge()
        assert isinstance(bridge, SecureProtocolBridge)
    
    def test_verify_and_convert_valid(self) -> None:
        """测试有效验证和转换"""
        bridge = create_secure_protocol_bridge()
        
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        
        import hashlib
        expected_sig = hashlib.sha256(
            f"did:agent-1:{mcp_msg.message_id}".encode()
        ).hexdigest()
        
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", expected_sig
        )
        
        assert task is not None
        assert task.agent_id == "agent-2"
    
    def test_verify_and_convert_invalid_signature(self) -> None:
        """测试无效签名"""
        bridge = create_secure_protocol_bridge()
        
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        
        task = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", "invalid-signature"
        )
        
        assert task is None
    
    def test_replay_protection(self) -> None:
        """测试重放保护"""
        bridge = create_secure_protocol_bridge()
        
        mcp_msg = MCPMessage(message_id="msg-1", method="tools/call", params={})
        
        import hashlib
        expected_sig = hashlib.sha256(
            f"did:agent-1:{mcp_msg.message_id}".encode()
        ).hexdigest()
        
        # 第一次转换应该成功
        task1 = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", expected_sig
        )
        assert task1 is not None
        
        # 第二次转换应该失败（重放）
        task2 = bridge.verify_and_convert_mcp_to_a2a(
            mcp_msg, "agent-2", "did:agent-1", expected_sig
        )
        assert task2 is None
    
    def test_add_replay_protection(self) -> None:
        """测试添加重放保护字段"""
        bridge = create_secure_protocol_bridge()
        
        message = {"id": "msg-1", "method": "tools/call"}
        protected = bridge.add_replay_protection(message)
        
        assert "nonce" in protected
        assert "timestamp" in protected
        assert protected["id"] == "msg-1"
