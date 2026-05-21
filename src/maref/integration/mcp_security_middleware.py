"""
MCP Security Middleware — 协议级安全中间件

提供独立于 MCPSecurityGate 的协议级安全功能：
- P3.1: 协议级输入验证 (JSONRPC 格式、参数类型、大小限制)
- P3.2: 可插拔速率限制
- P3.3: 可插拔审计日志

设计为中间件链，可按顺序处理请求。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from maref.integration.mcp_transport import JSONRPCRequest, JSONRPCResponse


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class MiddlewareResult:
    """中间件处理结果"""
    is_allowed: bool
    verdict: str = "ALLOW"
    reason: str = ""


class MCPProtocolValidator:
    """P3.1: MCP 协议请求验证器。

    验证 JSONRPC 请求格式、参数类型、大小限制等。
    """

    def __init__(self, max_request_size: int = 1024 * 1024) -> None:
        self.max_request_size = max_request_size

    def validate(self, request: JSONRPCRequest) -> ValidationResult:
        errors: list[str] = []

        # 1. 检查 jsonrpc 版本
        if not request.jsonrpc or request.jsonrpc != "2.0":
            errors.append(f"Invalid jsonrpc version: '{request.jsonrpc}', expected '2.0'")

        # 2. 检查 method
        if not request.method or not isinstance(request.method, str):
            errors.append("Method must be a non-empty string")
        elif not self._is_valid_method_name(request.method):
            errors.append(f"Method name contains invalid characters: {request.method}")

        # 3. 检查 id
        if request.id == "" or request.id is None:
            errors.append("Request id is required")

        # 4. 检查 params 类型
        if request.params is not None and not isinstance(request.params, dict):
            errors.append("Params must be a dict or None")

        # 5. 请求大小检查
        request_size = len(str(request).encode("utf-8"))
        if request_size > self.max_request_size:
            errors.append(f"Request size {request_size} exceeds maximum {self.max_request_size}")

        # 6. 方法特定参数检查
        if request.method == "tools/call":
            if not request.params or "name" not in request.params:
                errors.append("tools/call requires 'name' in params")

        if request.method == "resources/read":
            if not request.params or "uri" not in request.params:
                errors.append("resources/read requires 'uri' in params")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    @staticmethod
    def _is_valid_method_name(method: str) -> bool:
        """验证方法名是否安全（无路径遍历等）。"""
        if ".." in method or method.startswith("/") or "\\" in method:
            return False
        # 只允许字母、数字、下划线、斜杠
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/")
        return all(c in allowed_chars for c in method)


class MCPRateLimitMiddleware:
    """P3.2: MCP 速率限制中间件。

    基于滑动窗口的速率限制，每个 agent 独立计数。
    """

    def __init__(self, max_calls: int = 100, window_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def process(self, request: JSONRPCRequest, agent_id: str = "default") -> MiddlewareResult:
        with self._lock:
            now = time.time()
            window = self._windows[agent_id]

            # 清理过期时间戳
            cutoff = now - self.window_seconds
            while window and window[0] < cutoff:
                window.pop(0)

            if len(window) >= self.max_calls:
                return MiddlewareResult(
                    is_allowed=False,
                    verdict="DENY",
                    reason=f"Rate limit exceeded: {self.max_calls} calls per {self.window_seconds}s",
                )

            window.append(now)
            return MiddlewareResult(is_allowed=True, verdict="ALLOW")


class MCPAuditMiddleware:
    """P3.3: MCP 审计日志中间件。

    记录每个请求的处理结果。
    """

    def __init__(self, log_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.log_sink = log_sink

    def process(
        self,
        request: JSONRPCRequest,
        agent_id: str = "unknown",
        verdict: str = "ALLOW",
        reason: str = "",
    ) -> None:
        log_entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "method": request.method,
            "id": request.id,
            "verdict": verdict,
            "reason": reason,
        }

        # 如果请求包含 tool/resource 信息，也记录
        if request.params:
            if "name" in request.params:
                log_entry["tool_name"] = request.params["name"]
            if "uri" in request.params:
                log_entry["resource_uri"] = request.params["uri"]

        if self.log_sink is not None:
            self.log_sink(log_entry)


class MCPSecurityMiddleware:
    """P3: MCP 安全中间件链。

    组合协议验证、速率限制、审计日志，按顺序处理请求。

    使用方式:
        middleware = MCPSecurityMiddleware()
        result = middleware.process(request, agent_id="agent-1")
        if not result.is_allowed:
            return JSONRPCResponse(error={"code": -32000, "message": result.reason})
    """

    def __init__(
        self,
        max_request_size: int = 1024 * 1024,
        rate_limit_max_calls: int = 100,
        rate_limit_window: int = 60,
        audit_log_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.validator = MCPProtocolValidator(max_request_size=max_request_size)
        self.rate_limiter = MCPRateLimitMiddleware(
            max_calls=rate_limit_max_calls,
            window_seconds=rate_limit_window,
        )
        self.audit = MCPAuditMiddleware(log_sink=audit_log_sink)

    def process(self, request: JSONRPCRequest, agent_id: str = "default") -> MiddlewareResult:
        # 1. 协议验证
        validation = self.validator.validate(request)
        if not validation.is_valid:
            reason = validation.errors[0] if validation.errors else "Protocol validation failed"
            self.audit.process(request, agent_id, verdict="DENY", reason=reason)
            return MiddlewareResult(
                is_allowed=False,
                verdict="DENY",
                reason=reason,
            )

        # 2. 速率限制
        rate_result = self.rate_limiter.process(request, agent_id)
        if not rate_result.is_allowed:
            self.audit.process(
                request, agent_id, verdict="DENY", reason=rate_result.reason
            )
            return rate_result

        # 3. 通过 — 记录审计
        self.audit.process(request, agent_id, verdict="ALLOW")
        return MiddlewareResult(is_allowed=True, verdict="ALLOW")
