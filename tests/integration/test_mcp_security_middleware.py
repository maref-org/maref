from __future__ import annotations

import pytest

from maref.integration.mcp_security_middleware import (
    MCPSecurityMiddleware,
    MCPProtocolValidator,
    MCPAuditMiddleware,
    MCPRateLimitMiddleware,
)
from maref.integration.mcp_transport import JSONRPCRequest, JSONRPCResponse


class TestMCPProtocolValidator:
    """P3.1: 协议级输入验证测试"""

    def test_valid_jsonrpc_request(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/list", id=1)
        result = validator.validate(req)
        assert result.is_valid is True
        assert result.errors == []

    def test_missing_jsonrpc_version(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/list", id=1)
        req.jsonrpc = ""  # 空版本
        result = validator.validate(req)
        assert result.is_valid is False
        assert "jsonrpc" in result.errors[0]

    def test_invalid_method_name(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="", id=1)
        result = validator.validate(req)
        assert result.is_valid is False
        assert "Method" in result.errors[0]

    def test_missing_id(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/list", id="")
        result = validator.validate(req)
        assert result.is_valid is False
        assert "id" in result.errors[0]

    def test_invalid_params_type(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/call", id=1)
        req.params = "not_a_dict"  # 应该是 dict
        result = validator.validate(req)
        assert result.is_valid is False
        assert "Params" in result.errors[0]

    def test_method_name_sanitization(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/../../../etc/passwd", id=1)
        result = validator.validate(req)
        assert result.is_valid is False
        assert "invalid" in result.errors[0].lower()

    def test_request_size_limit(self):
        validator = MCPProtocolValidator(max_request_size=1024)
        req = JSONRPCRequest(method="tools/call", id=1)
        req.params = {"data": "x" * 2000}  # 超大参数
        result = validator.validate(req)
        assert result.is_valid is False
        assert "size" in result.errors[0].lower()

    def test_tools_call_requires_name(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="tools/call", id=1)
        req.params = {"arguments": {}}  # 缺少 name
        result = validator.validate(req)
        assert result.is_valid is False
        assert "name" in result.errors[0]

    def test_resources_read_requires_uri(self):
        validator = MCPProtocolValidator()
        req = JSONRPCRequest(method="resources/read", id=1)
        req.params = {}  # 缺少 uri
        result = validator.validate(req)
        assert result.is_valid is False
        assert "uri" in result.errors[0]


class TestMCPRateLimitMiddleware:
    """P3.2: 速率限制中间件测试"""

    def test_rate_limit_allows_under_limit(self):
        middleware = MCPRateLimitMiddleware(max_calls=3, window_seconds=60)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        for i in range(3):
            result = middleware.process(req, agent_id="agent-1")
            assert result.is_allowed is True

    def test_rate_limit_blocks_over_limit(self):
        middleware = MCPRateLimitMiddleware(max_calls=2, window_seconds=60)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1")  # 第1次
        middleware.process(req, agent_id="agent-1")  # 第2次
        result = middleware.process(req, agent_id="agent-1")  # 第3次 — 应被阻止
        
        assert result.is_allowed is False
        assert "rate" in result.reason.lower()

    def test_rate_limit_per_agent_isolation(self):
        middleware = MCPRateLimitMiddleware(max_calls=2, window_seconds=60)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1")
        middleware.process(req, agent_id="agent-1")
        
        # agent-2 不受 agent-1 的限制影响
        result = middleware.process(req, agent_id="agent-2")
        assert result.is_allowed is True

    def test_rate_limit_window_expires(self):
        import time
        middleware = MCPRateLimitMiddleware(max_calls=1, window_seconds=0)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1")  # 第1次
        time.sleep(0.01)  # 窗口过期
        
        result = middleware.process(req, agent_id="agent-1")  # 应允许
        assert result.is_allowed is True

    def test_rate_limit_without_agent_id_uses_default(self):
        middleware = MCPRateLimitMiddleware(max_calls=1, window_seconds=60)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req)  # 无 agent_id，使用 default
        result = middleware.process(req)  # 第2次应被阻止
        assert result.is_allowed is False


class TestMCPAuditMiddleware:
    """P3.3: 审计日志中间件测试"""

    def test_audit_logs_request(self):
        logs = []
        middleware = MCPAuditMiddleware(log_sink=logs.append)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1", verdict="ALLOW")
        
        assert len(logs) == 1
        assert logs[0]["method"] == "tools/list"
        assert logs[0]["agent_id"] == "agent-1"
        assert logs[0]["verdict"] == "ALLOW"

    def test_audit_logs_tool_call(self):
        logs = []
        middleware = MCPAuditMiddleware(log_sink=logs.append)
        req = JSONRPCRequest(method="tools/call", id=1)
        req.params = {"name": "bash", "arguments": {"command": "ls"}}
        
        middleware.process(req, agent_id="agent-1", verdict="DENY")
        
        assert len(logs) == 1
        assert logs[0]["tool_name"] == "bash"
        assert logs[0]["verdict"] == "DENY"

    def test_audit_includes_timestamp(self):
        import time
        logs = []
        middleware = MCPAuditMiddleware(log_sink=logs.append)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        before = time.time()
        middleware.process(req, agent_id="agent-1", verdict="ALLOW")
        after = time.time()
        
        assert before <= logs[0]["timestamp"] <= after

    def test_audit_without_log_sink_does_not_crash(self):
        middleware = MCPAuditMiddleware(log_sink=None)
        req = JSONRPCRequest(method="tools/list", id=1)
        
        # 不应抛出异常
        middleware.process(req, agent_id="agent-1", verdict="ALLOW")


class TestMCPSecurityMiddleware:
    """P3: 完整安全中间件链测试"""

    def test_middleware_chain_allows_valid_request(self):
        middleware = MCPSecurityMiddleware(
            rate_limit_max_calls=10,
            rate_limit_window=60,
        )
        req = JSONRPCRequest(method="tools/list", id=1)
        
        result = middleware.process(req, agent_id="agent-1")
        assert result.is_allowed is True
        assert result.verdict == "ALLOW"

    def test_middleware_chain_blocks_invalid_request(self):
        middleware = MCPSecurityMiddleware()
        req = JSONRPCRequest(method="", id=1)  # 无效方法
        
        result = middleware.process(req, agent_id="agent-1")
        assert result.is_allowed is False
        assert result.verdict == "DENY"

    def test_middleware_chain_blocks_rate_limited(self):
        middleware = MCPSecurityMiddleware(
            rate_limit_max_calls=1,
            rate_limit_window=60,
        )
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1")
        result = middleware.process(req, agent_id="agent-1")
        
        assert result.is_allowed is False
        assert "rate" in result.reason.lower()

    def test_middleware_audit_logging(self):
        logs = []
        middleware = MCPSecurityMiddleware(
            rate_limit_max_calls=10,
            audit_log_sink=logs.append,
        )
        req = JSONRPCRequest(method="tools/list", id=1)
        
        middleware.process(req, agent_id="agent-1")
        
        assert len(logs) == 1
        assert logs[0]["method"] == "tools/list"

    def test_middleware_chain_order(self):
        """验证中间件按正确顺序执行：验证 -> 速率限制 -> 审计"""
        logs = []
        middleware = MCPSecurityMiddleware(
            rate_limit_max_calls=1,
            rate_limit_window=60,
            audit_log_sink=logs.append,
        )
        req = JSONRPCRequest(method="tools/list", id=1)
        
        # 第1次：通过
        result1 = middleware.process(req, agent_id="agent-1")
        assert result1.is_allowed is True
        
        # 第2次：被速率限制阻止
        result2 = middleware.process(req, agent_id="agent-1")
        assert result2.is_allowed is False
        
        # 验证审计日志记录了2次（包括被拒绝的）
        assert len(logs) == 2
        assert logs[1]["verdict"] == "DENY"

    def test_middleware_blocks_tools_call_without_name(self):
        middleware = MCPSecurityMiddleware()
        req = JSONRPCRequest(method="tools/call", id=1)
        req.params = {"arguments": {}}
        
        result = middleware.process(req, agent_id="agent-1")
        assert result.is_allowed is False
        assert "name" in result.reason.lower()
