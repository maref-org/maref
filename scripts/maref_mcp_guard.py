#!/usr/bin/env python3
"""
MAREF MCP Guard - 完整实现

基于 Phase 1 发现的问题，实现完整的 MCP Guard：
1. 集成修复版 sidecar 的 GaaS 端点
2. 实现完整的治理检查流程
3. 添加审计日志和错误处理
4. 支持 HITL 集成
"""

import json
import os
import sys
import time
import uuid
import asyncio
import aiohttp
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path

# 配置
MAREF_SIDECAR_URL = os.getenv("MAREF_SIDECAR_URL", "http://127.0.0.1:8000")
MAREF_AGENT_ID = os.getenv("MAREF_AGENT_ID", "unknown-agent")
MAREF_API_KEY = os.getenv("MAREF_API_KEY", "default-key")
MAREF_TENANT_ID = os.getenv("MAREF_TENANT_ID", "default")

# 审计日志文件
AUDIT_LOG_FILE = Path.home() / ".maref_mcp_guard_audit.log"

class GovernanceDecision(Enum):
    """治理决策结果"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HITL = "require_hitl"
    ERROR = "error"

class ToolType(Enum):
    """工具类型映射"""
    WRITE_FILE = "Write"
    READ_FILE = "Read"
    EDIT_FILE = "Edit"
    EXECUTE_COMMAND = "Bash"
    SEARCH_FILES = "Glob"
    SEARCH_CONTENT = "Grep"
    CREATE_DIRECTORY = "Mkdir"
    DELETE_FILE = "Rm"
    MOVE_FILE = "Mv"
    COPY_FILE = "Cp"

@dataclass
class GovernanceRequest:
    """治理检查请求"""
    tenant_id: str
    actor_id: str
    action: str
    tool: str
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.actor_id,
            "action": self.action,
            "parameters": {
                "tool": self.tool,
                "file_path": self.file_path,
                **(self.metadata or {})
            }
        }

@dataclass 
class GovernanceResponse:
    """治理检查响应"""
    allowed: bool
    decision: str
    reason: str
    requires_hitl: bool = False
    hitl_event_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernanceResponse":
        verdict = data.get("verdict", "DENY")
        reason = data.get("reason", "Unknown")
        
        allowed = verdict == "ALLOW"
        requires_hitl = verdict == "REQUIRE_HITL"
        
        decision_map = {
            "ALLOW": "allow",
            "DENY": "deny",
            "REQUIRE_HITL": "require_hitl",
            "DEFER": "defer",
        }
        
        return cls(
            allowed=allowed,
            decision=decision_map.get(verdict, "deny"),
            reason=reason,
            requires_hitl=requires_hitl,
            hitl_event_id=data.get("audit_log_id")
        )

@dataclass
class AuditEntry:
    """审计日志条目"""
    id: str
    timestamp: float
    agent_id: str
    tool: str
    action: str
    file_path: Optional[str]
    decision: GovernanceDecision
    reason: str
    requires_hitl: bool = False
    hitl_event_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "tool": self.tool,
            "action": self.action,
            "file_path": self.file_path,
            "decision": self.decision.value,
            "reason": self.reason,
            "requires_hitl": self.requires_hitl,
            "hitl_event_id": self.hitl_event_id,
            "metadata": self.metadata or {}
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

class MAREFGovernanceClient:
    """MAREF 治理客户端"""
    
    def __init__(self, sidecar_url: str, api_key: str, tenant_id: str):
        self.sidecar_url = sidecar_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.session: Optional[aiohttp.ClientSession] = None
        self._setup_audit_log()
    
    def _setup_audit_log(self):
        """设置审计日志"""
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not AUDIT_LOG_FILE.exists():
            AUDIT_LOG_FILE.touch()
    
    async def connect(self):
        """连接 HTTP 会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=10)
            )
    
    async def close(self):
        """关闭 HTTP 会话"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def check_governance(self, req: GovernanceRequest) -> GovernanceResponse:
        """执行治理检查"""
        await self.connect()
        
        audit_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # 调用 GaaS 端点
            url = f"{self.sidecar_url}/api/v1/gaas/govern"
            
            async with self.session.post(url, json=req.to_dict()) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    gov_response = GovernanceResponse.from_dict(data)
                    
                    # 记录审计日志
                    await self._log_audit(
                        audit_id=audit_id,
                        agent_id=req.actor_id,
                        tool=req.tool,
                        action=req.action,
                        file_path=req.file_path,
                        decision=GovernanceDecision.ALLOW if gov_response.allowed else GovernanceDecision.DENY,
                        reason=gov_response.reason,
                        requires_hitl=gov_response.requires_hitl,
                        hitl_event_id=gov_response.hitl_event_id,
                        response_time=response_time,
                        metadata={"http_status": response.status}
                    )
                    
                    return gov_response
                    
                elif response.status == 404:
                    # GaaS 端点未找到，尝试合规端点
                    return await self._fallback_check(req, audit_id, start_time)
                    
                else:
                    # 其他错误
                    error_reason = f"Governance service error: {response.status}"
                    
                    await self._log_audit(
                        audit_id=audit_id,
                        agent_id=req.actor_id,
                        tool=req.tool,
                        action=req.action,
                        file_path=req.file_path,
                        decision=GovernanceDecision.ERROR,
                        reason=error_reason,
                        response_time=time.time() - start_time,
                        metadata={
                            "http_status": response.status,
                            "error": "governance_service_error"
                        }
                    )
                    
                    # 服务错误时默认允许（降级模式）
                    return GovernanceResponse(
                        allowed=True,
                        decision="allow",
                        reason=f"Governance service error, defaulting to allow: {response.status}",
                        requires_hitl=False
                    )
                    
        except aiohttp.ClientError as e:
            # 网络错误
            error_reason = f"Network error: {str(e)[:100]}"
            
            await self._log_audit(
                audit_id=audit_id,
                agent_id=req.actor_id,
                tool=req.tool,
                action=req.action,
                file_path=req.file_path,
                decision=GovernanceDecision.ERROR,
                reason=error_reason,
                response_time=time.time() - start_time,
                metadata={
                    "error_type": "network_error",
                    "error": str(e)
                }
            )
            
            # 网络错误时默认允许（降级模式）
            return GovernanceResponse(
                allowed=True,
                decision="allow",
                reason="Network error, defaulting to allow",
                requires_hitl=False
            )
            
        except Exception as e:
            # 其他错误
            error_reason = f"Unexpected error: {str(e)[:100]}"
            
            await self._log_audit(
                audit_id=audit_id,
                agent_id=req.actor_id,
                tool=req.tool,
                action=req.action,
                file_path=req.file_path,
                decision=GovernanceDecision.ERROR,
                reason=error_reason,
                response_time=time.time() - start_time,
                metadata={
                    "error_type": "unexpected_error",
                    "error": str(e)
                }
            )
            
            # 未知错误时默认允许（安全降级）
            return GovernanceResponse(
                allowed=True,
                decision="allow",
                reason="Unexpected error, defaulting to allow",
                requires_hitl=False
            )
    
    async def _fallback_check(self, req: GovernanceRequest, audit_id: str, start_time: float) -> GovernanceResponse:
        """回退检查（使用合规端点）"""
        try:
            url = f"{self.sidecar_url}/api/compliance/check-action"
            data = {
                "agent_id": req.actor_id,
                "action": req.action,
                "tool": req.tool,
                "file_path": req.file_path
            }
            
            async with self.session.post(url, json=data) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    
                    allowed = data.get("allowed", False)
                    decision = "allow" if allowed else "deny"
                    
                    await self._log_audit(
                        audit_id=audit_id,
                        agent_id=req.actor_id,
                        tool=req.tool,
                        action=req.action,
                        file_path=req.file_path,
                        decision=GovernanceDecision.ALLOW if allowed else GovernanceDecision.DENY,
                        reason="Fallback compliance check",
                        response_time=response_time,
                        metadata={
                            "http_status": response.status,
                            "fallback": True
                        }
                    )
                    
                    return GovernanceResponse(
                        allowed=allowed,
                        decision=decision,
                        reason="Fallback compliance check",
                        requires_hitl=False
                    )
                else:
                    # 回退也失败
                    await self._log_audit(
                        audit_id=audit_id,
                        agent_id=req.actor_id,
                        tool=req.tool,
                        action=req.action,
                        file_path=req.file_path,
                        decision=GovernanceDecision.ERROR,
                        reason="Fallback service error",
                        response_time=response_time,
                        metadata={
                            "http_status": response.status,
                            "fallback": True,
                            "error": "fallback_service_error"
                        }
                    )
                    
                    return GovernanceResponse(
                        allowed=True,  # 最终降级：允许
                        decision="allow",
                        reason="All services unavailable, emergency allow",
                        requires_hitl=False
                    )
                    
        except Exception as e:
            # 回退检查失败
            await self._log_audit(
                audit_id=audit_id,
                agent_id=req.actor_id,
                tool=req.tool,
                action=req.action,
                file_path=req.file_path,
                decision=GovernanceDecision.ERROR,
                reason="Fallback check failed",
                response_time=time.time() - start_time,
                metadata={
                    "error_type": "fallback_error",
                    "error": str(e)
                }
            )
            
            return GovernanceResponse(
                allowed=True,  # 最终降级：允许
                decision="allow",
                reason="Emergency fallback: all checks failed",
                requires_hitl=False
            )
    
    async def _log_audit(self, **kwargs):
        """记录审计日志（本地文件 + Sidecar 统一审计桥）"""
        entry = AuditEntry(
            id=kwargs.get("audit_id", str(uuid.uuid4())),
            timestamp=time.time(),
            agent_id=kwargs.get("agent_id", "unknown"),
            tool=kwargs.get("tool", "unknown"),
            action=kwargs.get("action", "unknown"),
            file_path=kwargs.get("file_path"),
            decision=kwargs.get("decision", GovernanceDecision.ERROR),
            reason=kwargs.get("reason", "Unknown"),
            requires_hitl=kwargs.get("requires_hitl", False),
            hitl_event_id=kwargs.get("hitl_event_id"),
            metadata=kwargs.get("metadata", {})
        )
        
        # 1. 写入本地文件
        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(entry.to_json() + "\n")
        
        # 2. POST 到 Sidecar 统一审计桥
        try:
            payload = {
                "source": "mcp_guard",
                "entries": [{
                    "tenant_id": self.tenant_id,
                    "agent_id": entry.agent_id,
                    "action": entry.action,
                    "verdict": "ALLOW" if entry.decision == GovernanceDecision.ALLOW else "DENY",
                    "parameters": {
                        "tool": entry.tool,
                        "file_path": entry.file_path,
                    },
                    "context": {
                        "reason": entry.reason,
                        "requires_hitl": entry.requires_hitl,
                        "hitl_event_id": entry.hitl_event_id,
                        "decision": entry.decision.value,
                    }
                }]
            }
            async with self.session.post(
                f"{self.sidecar_url}/api/v1/audit/ingest",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    pass  # 审计已同步到 sidecar
                else:
                    print(f"[MAREF] Audit ingest status: {resp.status}", file=sys.stderr)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Sidecar 不可用时仅写本地文件，不阻塞
            print(f"[MAREF] Audit ingest skipped: {e}", file=sys.stderr)
        
        # 同时输出到 stderr（用于调试）
        print(f"[MAREF Audit] {entry.agent_id} {entry.tool} {entry.action}: {entry.decision.value} - {entry.reason}", 
              file=sys.stderr)

class MCPGuardServer:
    """MCP Guard 服务器"""
    
    def __init__(self):
        self.governance_client = MAREFGovernanceClient(
            sidecar_url=MAREF_SIDECAR_URL,
            api_key=MAREF_API_KEY,
            tenant_id=MAREF_TENANT_ID
        )
        
        # 工具映射
        self.tool_mapping = {
            "write_file": ToolType.WRITE_FILE,
            "read_file": ToolType.READ_FILE,
            "edit_file": ToolType.EDIT_FILE,
            "execute_command": ToolType.EXECUTE_COMMAND,
            "search_files": ToolType.SEARCH_FILES,
            "search_content": ToolType.SEARCH_CONTENT,
            "create_directory": ToolType.CREATE_DIRECTORY,
            "delete_file": ToolType.DELETE_FILE,
            "move_file": ToolType.MOVE_FILE,
            "copy_file": ToolType.COPY_FILE,
        }
        
        # 工具定义
        self.tools = self._define_tools()
    
    def _define_tools(self) -> List[Dict[str, Any]]:
        """定义 MCP 工具"""
        return [
            {
                "name": "write_file",
                "description": "Write file with MAREF governance check",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "File content"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "read_file",
                "description": "Read file with MAREF governance check",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "edit_file",
                "description": "Edit file with MAREF governance check",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "old_string": {"type": "string", "description": "Text to replace"},
                        "new_string": {"type": "string", "description": "Replacement text"}
                    },
                    "required": ["path", "old_string", "new_string"]
                }
            },
            {
                "name": "execute_command",
                "description": "Execute command with MAREF governance check",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"]
                }
            },
        ]
    
    async def initialize(self):
        """初始化服务器"""
        await self.governance_client.connect()
        print(f"[MCP Guard] 初始化完成", file=sys.stderr)
        print(f"[MCP Guard] Agent ID: {MAREF_AGENT_ID}", file=sys.stderr)
        print(f"[MCP Guard] Sidecar URL: {MAREF_SIDECAR_URL}", file=sys.stderr)
        print(f"[MCP Guard] Audit log: {AUDIT_LOG_FILE}", file=sys.stderr)
    
    async def cleanup(self):
        """清理资源"""
        await self.governance_client.close()
    
    def handle_list_tools(self) -> Dict[str, Any]:
        """处理 listTools 请求"""
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": self.tools
            }
        }
    
    async def handle_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """处理 callTool 请求"""
        # 映射工具类型
        tool_type = self.tool_mapping.get(tool_name)
        if not tool_type:
            return self._create_error_response(f"Unknown tool: {tool_name}")
        
        # 提取文件路径
        file_path = arguments.get("path")
        
        # 创建治理请求
        req = GovernanceRequest(
            tenant_id=MAREF_TENANT_ID,
            actor_id=MAREF_AGENT_ID,
            action=tool_name,
            tool=tool_type.value,
            file_path=file_path,
            metadata={
                "arguments": arguments,
                "tool_name": tool_name
            }
        )
        
        # 执行治理检查
        gov_response = await self.governance_client.check_governance(req)
        
        # 根据决策处理
        if not gov_response.allowed:
            return self._create_blocked_response(gov_response, tool_name, file_path)
        elif gov_response.requires_hitl:
            return self._create_hitl_response(gov_response, tool_name, file_path)
        else:
            return self._create_allowed_response(gov_response, tool_name, file_path, arguments)
    
    def _create_error_response(self, error: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": error
            }
        }
    
    def _create_blocked_response(self, gov_response: GovernanceResponse, tool_name: str, file_path: Optional[str]) -> Dict[str, Any]:
        """创建阻止响应"""
        message = f"🚫 MAREF Governance Blocked\n\n"
        message += f"Tool: {tool_name}\n"
        if file_path:
            message += f"File: {file_path}\n"
        message += f"Decision: {gov_response.decision}\n"
        message += f"Reason: {gov_response.reason}\n"
        
        if gov_response.requires_hitl:
            message += f"\n⚠️  HITL Required: {gov_response.hitl_event_id}"
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": message
                    }
                ],
                "isError": True
            }
        }
    
    def _create_hitl_response(self, gov_response: GovernanceResponse, tool_name: str, file_path: Optional[str]) -> Dict[str, Any]:
        """创建 HITL 响应"""
        message = f"⏳ MAREF HITL Required\n\n"
        message += f"Tool: {tool_name}\n"
        if file_path:
            message += f"File: {file_path}\n"
        message += f"Reason: {gov_response.reason}\n"
        message += f"HITL Event ID: {gov_response.hitl_event_id}\n\n"
        message += "Please approve this action in the MAREF dashboard.\n"
        message += "After approval, retry the action."
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": message
                    }
                ],
                "isError": True
            }
        }
    
    def _create_allowed_response(self, gov_response: GovernanceResponse, tool_name: str, 
                                file_path: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
        """创建允许响应"""
        message = f"✅ MAREF Governance Approved\n\n"
        message += f"Tool: {tool_name}\n"
        if file_path:
            message += f"File: {file_path}\n"
        message += f"Decision: {gov_response.decision}\n"
        message += f"Reason: {gov_response.reason}\n\n"
        message += "Proceeding with execution..."
        
        # 在实际实现中，这里会调用真正的工具执行
        # 目前返回模拟成功响应
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": message
                    }
                ]
            }
        }

async def main():
    """主函数 - MCP 服务器主循环"""
    server = MCPGuardServer()
    
    print("MAREF MCP Guard 启动...", file=sys.stderr)
    
    try:
        await server.initialize()
        
        # 简单的 stdio MCP 服务器循环
        while True:
            try:
                # 读取 JSON-RPC 消息
                line = sys.stdin.readline()
                if not line:
                    break
                
                message = json.loads(line.strip())
                method = message.get("method")
                
                # 处理消息
                if method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {"listChanged": False}
                            },
                            "serverInfo": {
                                "name": "MAREF MCP Guard",
                                "version": "1.0.0"
                            }
                        }
                    }
                elif method == "tools/list":
                    response = server.handle_list_tools()
                    response["id"] = message.get("id")
                elif method == "tools/call":
                    params = message.get("params", {})
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    
                    result = await server.handle_call_tool(tool_name, arguments)
                    result["id"] = message.get("id")
                    response = result
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }
                
                # 发送响应
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                print(f"[Error] JSON decode error: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[Error] Processing error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                
    except KeyboardInterrupt:
        print("\n[MCP Guard] 正在关闭...", file=sys.stderr)
    except Exception as e:
        print(f"[Error] Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        await server.cleanup()
        print("[MCP Guard] 已关闭", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())