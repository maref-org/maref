from __future__ import annotations

import os
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from maref.governance import AuditLogger, CircuitBreaker, GovernanceStateMachine
from maref.immunity.cooldown_manager import CooldownManager
from maref.immunity.negative_gene_bank import NegativeGeneBank
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_server import create_a2a_router
from maref.mcp.evolution_tools import EVOLUTION_TOOLS
from maref.mcp.router import MCPServerAdapter
from maref.observability.guardrail_metrics import get_guardrail_metrics
from maref.observability.metric_store import MetricStore
from maref.observability.security_headers_middleware import SecurityHeadersMiddleware
from maref.recursive.cost_tracker import CostTracker
from maref.tool.registry import ToolRegistry
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.gaas_router import router as gaas_router
from sidecar.mcp_bridge import SIDECAR_MCP_TOOLS, SidecarMCPBridge
from sidecar.mcp_gateway import MCPGateway, create_mcp_gateway_router
from sidecar.monitor import CompositeMonitor
from sidecar.obs_bridge import ObsBridge

_sessions: dict[str, dict[str, Any]] = {}
_messages: dict[str, list[dict[str, Any]]] = {}
_providers: dict[str, dict[str, Any]] = {
    "ollama": {"id": "ollama", "name": "Ollama", "models": ["gemma3:4b"], "defaultModel": "gemma3:4b"},
    "bailian": {"id": "bailian", "name": "阿里云百炼", "models": ["deepseek-v4-pro"], "defaultModel": "deepseek-v4-pro"},
    "siliconflow": {"id": "siliconflow", "name": "SiliconFlow", "models": ["deepseek-v4"], "defaultModel": "deepseek-v4"},
    "openai": {"id": "openai", "name": "OpenAI", "models": ["gpt-4o"], "defaultModel": "gpt-4o"},
    "anthropic": {"id": "anthropic", "name": "Anthropic", "models": ["claude-4"], "defaultModel": "claude-4"},
}
_skills: dict[str, dict[str, Any]] = {
    "file-browser": {"id": "file-browser", "name": "File Browser"},
    "git-ops": {"id": "git-ops", "name": "Git Ops"},
    "terminal": {"id": "terminal", "name": "Terminal"},
    "web-search": {"id": "web-search", "name": "Web Search"},
    "code-edit": {"id": "code-edit", "name": "Code Edit"},
}
_tasks: dict[str, dict[str, Any]] = {
    "task-1": {"id": "task-1", "title": "Task 1"},
    "task-2": {"id": "task-2", "title": "Task 2"},
    "task-3": {"id": "task-3", "title": "Task 3"},
}
_compliance_agents: dict[str, dict[str, Any]] = {}
_compliance_audit_logs: dict[str, list[dict[str, Any]]] = {}

# Immunity system singletons
_cooldown_manager = CooldownManager()
_gene_bank = NegativeGeneBank()

_governance_state: dict[str, Any] = {
    "state": "OBSERVE",
    "entropy": 2,
    "entropy_max": 4,
    "transition_count": 147,
    "circuit_breaker": "CLOSED",
}
_transition_history: list[dict[str, Any]] = [
    {"from": "INIT", "to": "OBSERVE", "reason": "系统启动", "time": "14:00", "valid": True},
    {"from": "OBSERVE", "to": "ANALYZE", "reason": "探针读数就绪", "time": "14:01", "valid": True},
    {"from": "ANALYZE", "to": "EVALUATE", "reason": "风险评分达标", "time": "14:02", "valid": True},
    {"from": "EVALUATE", "to": "DECIDE", "reason": "策略评估完成", "time": "14:03", "valid": True},
    {"from": "DECIDE", "to": "ACT", "reason": "执行治理决策", "time": "14:04", "valid": True},
    {"from": "ACT", "to": "VERIFY", "reason": "操作执行完毕", "time": "14:05", "valid": True},
    {"from": "VERIFY", "to": "STABILIZE", "reason": "验证通过", "time": "14:06", "valid": True},
    {"from": "STABILIZE", "to": "REPORT", "reason": "稳定期结束", "time": "14:07", "valid": True},
    {"from": "REPORT", "to": "OBSERVE", "reason": "下一轮观察", "time": "14:08", "valid": True},
]
_circuit_breaker_events: list[dict[str, Any]] = [
    {"from": "CLOSED", "to": "OPEN", "reason": "连续失败 ≥ 5", "time": "13:45"},
    {"from": "OPEN", "to": "HALF_OPEN", "reason": "冷却期满 (30s)", "time": "13:46"},
    {"from": "HALF_OPEN", "to": "CLOSED", "reason": "探测通过", "time": "13:47"},
]
_oscillation_events: list[dict[str, Any]] = [
    {"stage": "DETECTED", "desc": "振荡率 12.0/s > 阈值 10.0", "time": "13:20"},
    {"stage": "STABILIZING", "desc": "强制执行 STABILIZE", "time": "13:20"},
    {"stage": "COOLDOWN", "desc": "冷却中 (30s)", "time": "13:21"},
    {"stage": "VERIFYING", "desc": "验证稳定 (率 2.0/s)", "time": "13:21"},
    {"stage": "ADJUSTED", "desc": "振荡修复完成", "time": "13:21"},
]
_audit_logs: list[dict[str, Any]] = [
    {"id": 1, "type": "transition", "actor": "StateMachine", "action": "INIT → OBSERVE", "reason": "系统启动", "severity": "INFO", "time": "2026-05-09 14:00:01"},
    {"id": 2, "type": "transition", "actor": "StateMachine", "action": "OBSERVE → ANALYZE", "reason": "探针读数就绪", "severity": "INFO", "time": "2026-05-09 14:01:23"},
    {"id": 3, "type": "decision", "actor": "GovernanceOverlay", "action": "ALLOW 操作", "reason": "安全门评估通过", "severity": "INFO", "time": "2026-05-09 14:03:45"},
    {"id": 4, "type": "anomaly", "actor": "DualThresholdDetector", "action": "anomaly_probe 超阈值", "reason": "主阈值 10.0 被触发", "severity": "WARN", "time": "2026-05-09 14:05:12"},
    {"id": 5, "type": "transition", "actor": "StateMachine", "action": "ACT → VERIFY", "reason": "操作执行完毕", "severity": "INFO", "time": "2026-05-09 14:06:30"},
    {"id": 6, "type": "decision", "actor": "CircuitBreaker", "action": "CLOSED → OPEN", "reason": "连续失败 5 次", "severity": "ERROR", "time": "2026-05-09 13:45:00"},
    {"id": 7, "type": "anomaly", "actor": "OscillationProbe", "action": "振荡检测触发", "reason": "频率 12.0/s > 阈值 10.0", "severity": "WARN", "time": "2026-05-09 13:20:00"},
    {"id": 8, "type": "operation", "actor": "DesktopAgent", "action": "click / Finder 窗口", "reason": "桌面自动化", "severity": "INFO", "time": "2026-05-09 13:15:00"},
    {"id": 9, "type": "transition", "actor": "StateMachine", "action": "STABILIZE → REPORT", "reason": "稳定期结束", "severity": "INFO", "time": "2026-05-09 13:10:00"},
    {"id": 10, "type": "decision", "actor": "HumanArbitration", "action": "APPROVE 漂移事件", "reason": "人工审批", "severity": "INFO", "time": "2026-05-09 12:55:00"},
    {"id": 11, "type": "anomaly", "actor": "LatencyProbe", "action": "延迟超标", "reason": "决策延迟 8ms > 阈值 5ms", "severity": "WARN", "time": "2026-05-09 12:40:00"},
    {"id": 12, "type": "operation", "actor": "DesktopAgent", "action": "type / 搜索 Documents", "reason": "桌面自动化", "severity": "INFO", "time": "2026-05-09 12:30:00"},
]
_hitl_events: dict[str, dict[str, Any]] = {
    "hitl-1": {
        "event_id": "hitl-1",
        "tier": "high",
        "severity": "WARN",
        "description": "检测到漂移事件，需人工审批",
        "action": "APPROVE 漂移事件",
        "timestamp": 1746788100,
        "auto_approve_seconds": 300,
        "status": "pending",
    },
    "hitl-2": {
        "event_id": "hitl-2",
        "tier": "critical",
        "severity": "ERROR",
        "description": "熔断器触发，需人工确认降级",
        "action": "确认降级策略",
        "timestamp": 1746787200,
        "auto_approve_seconds": 120,
        "status": "pending",
    },
}
_hitl_stats: dict[str, Any] = {
    "total_events": 2,
    "pending_count": 2,
    "by_tier": {"high": 1, "critical": 1},
    "by_status": {"pending": 2},
    "tier_map": {"high": "高", "critical": "严重", "medium": "中", "low": "低"},
}

_next_audit_id: int = 13
_ws_connections: list[WebSocket] = []


async def _broadcast_ws(event_type: str, data: dict[str, Any]) -> None:
    payload = {"type": event_type, **data}
    stale: list[WebSocket] = []
    for ws in _ws_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _ws_connections.remove(ws)


def create_a2a_bridge() -> A2ABridge:
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    cb = CircuitBreaker()
    return A2ABridge(state_machine=sm, audit_logger=audit, circuit_breaker=cb)


def _setup_routes(app: FastAPI, collector: ObservationCollector, monitor: CompositeMonitor, obs_bridge: ObsBridge | None = None) -> None:
    _metric_store = MetricStore()
    _cost_tracker = CostTracker(metric_store=_metric_store)
    mcp_bridge = SidecarMCPBridge(repo_path=os.getcwd())

    _tool_registry = ToolRegistry()
    for t in EVOLUTION_TOOLS:
        _tool_registry.register(t)
    _mcp_adapter = MCPServerAdapter(_tool_registry)

    gateway = MCPGateway()
    gateway.register_backend(
        prefix="maref_",
        transport_type="in-process",
        handler=mcp_bridge.handle_tool_call,
        tools=[t.to_dict() for t in SIDECAR_MCP_TOOLS],
    )
    gateway.register_backend(
        prefix="maref_evolution_",
        transport_type="in-process",
        handler=_mcp_adapter.handle_tool_call,
        tools=_mcp_adapter.list_tools(),
    )
    gateway_router = create_mcp_gateway_router(gateway)
    app.include_router(gateway_router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "collector_running": collector._running,
            "buffer_size": collector.get_buffer_size(),
        }

    @app.get("/api/agents")
    async def list_agents() -> dict[str, Any]:
        agents = await MockAgentAdapter().list_agents()
        return {"agents": [str(aid) for aid in agents]}

    @app.get("/api/observations")
    def get_observations() -> dict[str, Any]:
        obs_list = collector.get_recent()
        return {"count": len(obs_list), "observations": [o.to_dict() for o in obs_list]}

    @app.get("/api/anomalies")
    def get_anomalies() -> dict[str, Any]:
        return {"anomalies": []}

    @app.get("/api/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        gm = get_guardrail_metrics()
        return gm.get_metrics()

    @app.get("/api/v1/guardrails/stats")
    def guardrails_stats() -> dict[str, Any]:
        gm = get_guardrail_metrics()
        return gm.get_stats()

    @app.get("/api/v1/guardrails/events")
    def guardrails_events(limit: int = 50) -> dict[str, Any]:
        gm = get_guardrail_metrics()
        return {"events": gm.get_recent_events(limit=limit)}

    @app.get("/api/obs/status")
    def obs_status() -> dict[str, Any]:
        bridge_connected = obs_bridge is not None and obs_bridge.get_client() is not None
        return {"enabled": True, "level": "basic" if bridge_connected else "none", "bridge_connected": bridge_connected}

    @app.get("/api/red-metrics")
    def red_metrics() -> dict[str, Any]:
        return {"summary": {}, "by_path": {}}

    @app.post("/api/sessions")
    def create_session(body: dict[str, Any]) -> dict[str, Any]:
        session_id = str(uuid4())
        session = {
            "id": session_id,
            "title": body.get("title", ""),
            "mode": body.get("mode", "chat"),
            "provider": body.get("provider", ""),
            "model": body.get("model", ""),
            "status": "idle",
        }
        _sessions[session_id] = session
        _messages[session_id] = [{"role": "assistant", "content": "Welcome!"}]
        return session

    @app.get("/api/sessions")
    def list_sessions() -> dict[str, Any]:
        return {"sessions": list(_sessions.values())}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, Any]:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        _sessions.pop(session_id, None)
        _messages.pop(session_id, None)
        return {"deleted": True}

    @app.get("/api/sessions/{session_id}/messages")
    def get_messages(session_id: str) -> dict[str, Any]:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        msgs = _messages.get(session_id, [{"role": "assistant", "content": "Welcome!"}])
        return {"messages": msgs}

    @app.post("/api/sessions/{session_id}/messages")
    def send_message(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        content = body.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Empty content")
        msg = {"role": "user", "content": content}
        _messages.setdefault(session_id, []).append(msg)
        return msg

    @app.get("/api/sessions/{session_id}/stream")
    def stream_session(session_id: str) -> StreamingResponse:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        async def event_stream() -> Any:
            import asyncio
            yield "data: connected\n\n"
            while True:
                await asyncio.sleep(15)
                yield ": keepalive\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream; charset=utf-8")

    @app.post("/api/sessions/{session_id}/interrupt")
    def interrupt_session(session_id: str) -> dict[str, Any]:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"interrupted": False}

    @app.get("/api/providers")
    def list_providers() -> dict[str, Any]:
        return {"providers": list(_providers.values())}

    @app.post("/api/providers")
    def register_provider(provider: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(uuid4())
        provider["id"] = provider_id
        _providers[provider_id] = provider
        return provider

    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        return {"skills": list(_skills.values())}

    @app.get("/api/tasks")
    def list_tasks() -> dict[str, Any]:
        return {"tasks": list(_tasks.values())}

    @app.post("/api/tasks")
    def create_task(task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(uuid4())
        task["id"] = task_id
        _tasks[task_id] = task
        return task

    @app.get("/api/filetree")
    def get_filetree() -> dict[str, Any]:
        return {"roots": [], "files": []}

    @app.post("/api/compliance/register")
    def compliance_register(body: dict[str, Any]) -> dict[str, Any]:
        agent_id = body.get("agent_id", "")
        _compliance_agents[agent_id] = {
            "agent_id": agent_id,
            "data_residency": body.get("data_residency", ""),
            "model_backend": body.get("model_backend", ""),
            "governance_state": "active",
        }
        _compliance_audit_logs.setdefault(agent_id, []).append({
            "action": "register",
            "timestamp": str(uuid4()),
        })
        return {
            "agent_id": agent_id,
            "status": "registered",
            "governance_state": "active",
        }

    @app.get("/api/compliance/agents")
    def compliance_agents() -> dict[str, Any]:
        return {"agents": list(_compliance_agents.values())}

    @app.post("/api/compliance/check-action")
    def compliance_check_action(body: dict[str, Any]) -> dict[str, Any]:
        agent_id = body.get("agent_id", "")
        if agent_id not in _compliance_agents:
            return {"allowed": False, "decision": "deny"}
        return {"allowed": True, "decision": "allow"}

    @app.post("/api/compliance/snapshot")
    def compliance_snapshot(body: dict[str, Any]) -> dict[str, Any]:
        agent_id = body.get("agent_id", "")
        if agent_id not in _compliance_agents:
            return {"error": "Agent not found"}
        return {"snapshot": _compliance_agents.get(agent_id)}

    @app.get("/api/compliance/audit-log/{agent_id}")
    def compliance_audit_log(agent_id: str) -> dict[str, Any]:
        if agent_id not in _compliance_agents:
            return {"error": "Agent not found"}
        return {"audit_log": _compliance_audit_logs.get(agent_id, [])}

    @app.post("/api/mcp")
    async def mcp_jsonrpc(body: dict[str, Any]) -> dict[str, Any]:
        method = body.get("method", "")
        req_id = body.get("id", 0)

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": mcp_bridge.get_server_info(),
            }
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": mcp_bridge.list_tools()},
            }
        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": mcp_bridge.list_resources()},
            }
        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": mcp_bridge.list_prompts()},
            }
        if method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = mcp_bridge.handle_tool_call(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"},
        }

    @app.get("/api/mcp/.well-known")
    def mcp_well_known() -> dict[str, Any]:
        return {
            "protocol": "mcp",
            "version": "2024-11-05",
            "capabilities": {"tools": list(SIDECAR_MCP_TOOLS)},
        }

    @app.get("/api/status")
    def status() -> dict[str, str]:
        return {"status": "running"}

    @app.get("/api/version")
    def version() -> dict[str, str]:
        return {"version": "0.35.0-beta"}

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        _ws_connections.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in _ws_connections:
                _ws_connections.remove(websocket)

    @app.get("/api/immunity/cooldown")
    def list_cooldown_entries() -> dict[str, Any]:
        entries = _cooldown_manager.get_all_entries()
        return {
            "entries": [
                {
                    "cooldown_id": e.cooldown_id,
                    "agent_id": e.agent_id,
                    "status": e.status,
                    "submitted_at": e.submitted_at,
                    "contamination_index": e.contamination_index,
                    "blocked": e.blocked,
                    "merged": e.merged,
                    "force_merged": e.force_merged,
                }
                for e in entries
            ],
            "total": len(entries),
            "status": "ok",
        }

    @app.get("/api/immunity/cooldown/summary")
    def cooldown_summary() -> dict[str, Any]:
        entries = _cooldown_manager.get_all_entries()
        return {
            "total": len(entries),
            "cooling": sum(1 for e in entries if e.status == "cooling"),
            "blocked": sum(1 for e in entries if e.status == "blocked"),
            "merged": sum(1 for e in entries if e.merged),
            "force_merged": sum(1 for e in entries if e.force_merged),
            "status": "ok",
        }

    @app.get("/api/immunity/genes")
    def list_genes() -> dict[str, Any]:
        genes = _gene_bank.query_all()
        return {
            "genes": [
                {
                    "gene_id": g.gene_id,
                    "cwe_id": g.cwe_id,
                    "risk_level": g.risk_level,
                    "severity": g.severity,
                    "blocked": g.blocked,
                    "title": g.title,
                    "source": g.source,
                    "occurrences": g.occurrences,
                }
                for g in genes
            ],
            "total": len(genes),
            "status": "ok",
        }

    @app.get("/api/v1/governance/state")
    def governance_state() -> dict[str, Any]:
        return dict(_governance_state)

    @app.get("/api/v1/governance/transitions")
    def governance_transitions() -> dict[str, Any]:
        return {"transitions": list(_transition_history)}

    @app.get("/api/v1/governance/circuit-breaker")
    def governance_circuit_breaker() -> dict[str, Any]:
        return {"events": list(_circuit_breaker_events)}

    @app.get("/api/v1/governance/oscillation")
    def governance_oscillation() -> dict[str, Any]:
        return {"events": list(_oscillation_events)}

    @app.get("/api/v1/audit/logs")
    def audit_logs(type: str = "all", search: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        entries = _audit_logs
        if type and type != "all":
            entries = [e for e in entries if e["type"] == type]
        if search:
            q = search.lower()
            entries = [e for e in entries if q in e["actor"].lower() or q in e["action"].lower() or q in e["reason"].lower()]
        total = len(entries)
        sliced = entries[offset:offset + limit]
        counts = {"transition": 0, "decision": 0, "anomaly": 0, "operation": 0}
        for e in _audit_logs:
            t = e["type"]
            if t in counts:
                counts[t] += 1
        return {"entries": sliced, "total": total, "counts": counts}

    @app.get("/api/v1/audit/stats")
    def audit_stats() -> dict[str, Any]:
        counts: dict[str, int] = {}
        for e in _audit_logs:
            t = e["type"]
            counts[t] = counts.get(t, 0) + 1
        return {"counts": counts}

    @app.get("/api/v1/audit/chain")
    def audit_chain(session_id: str = "", limit: int = 50) -> dict[str, Any]:
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        for e in _audit_logs:
            ref = e.get("session_id", e.get("actor", ""))
            if session_id and session_id not in ref:
                continue
            dedup_key = f"{e.get('timestamp', '')}-{e.get('action', '')}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                chain.append(e)
        if hasattr(_verifier_loop, "get_history"):
            for h in _verifier_loop.get_history():
                chain.append({
                    "type": "verifier_check",
                    "action": h["action"],
                    "result": "passed" if h["passed"] else "blocked",
                    "agreement": h["agreement"],
                    "votes": h["votes"],
                    "session_id": session_id or "verifier",
                })
        chain.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"chain": chain[:limit], "total": len(chain)}

    @app.get("/api/v1/hitl/pending")
    def hitl_pending(tier: str = "") -> dict[str, Any]:
        events = [e for e in _hitl_events.values() if e["status"] == "pending"]
        if tier:
            events = [e for e in events if e["tier"] == tier]
        return {"events": list(events), "count": len(events)}

    @app.get("/api/v1/hitl/history")
    def hitl_history(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        all_events = list(_hitl_events.values())
        all_events.sort(key=lambda e: e["timestamp"], reverse=True)
        sliced = all_events[offset:offset + limit]
        return {"events": sliced, "count": len(sliced)}

    @app.get("/api/v1/hitl/stats")
    def hitl_stats() -> dict[str, Any]:
        return {"stats": dict(_hitl_stats)}

    @app.post("/api/v1/hitl/{event_id}/approve")
    def hitl_approve(event_id: str) -> dict[str, Any]:
        event = _hitl_events.get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="HITL event not found")
        if event["status"] != "pending":
            raise HTTPException(status_code=409, detail="Event is not pending")
        event["status"] = "approved"
        _hitl_stats["pending_count"] = max(0, _hitl_stats["pending_count"] - 1)
        _hitl_stats["by_status"]["pending"] = _hitl_stats["by_status"].get("pending", 1) - 1
        _hitl_stats["by_status"]["approved"] = _hitl_stats["by_status"].get("approved", 0) + 1
        return {"event_id": event_id, "status": "approved", "approved": True}

    @app.post("/api/v1/hitl/{event_id}/deny")
    def hitl_deny(event_id: str) -> dict[str, Any]:
        event = _hitl_events.get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="HITL event not found")
        if event["status"] != "pending":
            raise HTTPException(status_code=409, detail="Event is not pending")
        event["status"] = "rejected"
        _hitl_stats["pending_count"] = max(0, _hitl_stats["pending_count"] - 1)
        _hitl_stats["by_status"]["pending"] = _hitl_stats["by_status"].get("pending", 1) - 1
        _hitl_stats["by_status"]["rejected"] = _hitl_stats["by_status"].get("rejected", 0) + 1
        return {"event_id": event_id, "status": "rejected", "cancelled": True, "reason": event.get("description", "")}

    @app.post("/api/v1/hitl/request")
    def hitl_request(body: dict[str, Any]) -> dict[str, Any]:
        event_id = f"hitl-{str(uuid4())[:8]}"
        event = {
            "event_id": event_id,
            "tier": body.get("tier", "medium"),
            "severity": body.get("severity", "INFO"),
            "description": body.get("description", ""),
            "action": body.get("action", ""),
            "timestamp": int(time.time()),
            "auto_approve_seconds": body.get("auto_approve_seconds", 300),
            "status": "pending",
        }
        _hitl_events[event_id] = event
        _hitl_stats["total_events"] += 1
        _hitl_stats["pending_count"] += 1
        tier = event["tier"]
        _hitl_stats["by_tier"][tier] = _hitl_stats["by_tier"].get(tier, 0) + 1
        _hitl_stats["by_status"]["pending"] = _hitl_stats["by_status"].get("pending", 0) + 1
        return {
            "event_id": event_id,
            "status": "pending",
            "action": event["action"],
            "description": event["description"],
            "tier": event["tier"],
            "requires_human": True,
            "auto_approve_seconds": event["auto_approve_seconds"],
        }

    @app.get("/api/v1/observability/error-budget")
    def observability_error_budget() -> dict[str, Any]:
        stats = _metric_store.get_table_stats()
        total_requests = sum(stats.values())
        total_errors = int(_metric_store.query_aggregate("error", operation="count", table="telemetry_metrics"))
        budget_consumed = float(total_errors)
        budget_total = 5000.0
        remaining = max(0.0, budget_total - budget_consumed)
        remaining_pct = round(remaining / budget_total * 100, 2) if budget_total > 0 else 0.0
        burn_rate = round(total_errors / max(1, total_requests) * 100, 2) if total_requests > 0 else 0.0
        return {
            "slo_target": 0.995,
            "period_seconds": 2592000,
            "total_period_requests": total_requests,
            "budget": {
                "total": budget_total,
                "consumed": budget_consumed,
                "remaining": remaining,
                "remaining_pct": remaining_pct,
            },
            "burn_rate": burn_rate,
            "alerts": [
                {"level": "P0", "burn_rate": burn_rate, "threshold": 14.4, "window_seconds": 3600, "triggered": burn_rate > 14.4, "slo_name": "availability_0.995"},
                {"level": "P1", "burn_rate": burn_rate, "threshold": 6.0, "window_seconds": 21600, "triggered": burn_rate > 6.0, "slo_name": "availability_0.995"},
                {"level": "P2", "burn_rate": burn_rate, "threshold": 2.0, "window_seconds": 259200, "triggered": burn_rate > 2.0, "slo_name": "availability_0.995"},
            ],
            "budget_exhausted": remaining <= 0,
            "time_to_exhaustion_seconds": max(0, int(remaining / max(burn_rate, 0.01))) if burn_rate > 0 else 86400,
            "uptime_seconds": 3600,
            "total_errors": total_errors,
            "recent_errors": [
                {"id": "err-1", "severity": "ERROR", "source": "gateway", "message": "Request timeout", "timestamp": "2026-06-17T10:30:00Z"},
                {"id": "err-2", "severity": "WARN", "source": "guardrails", "message": "Risk score 0.85 exceeds threshold", "timestamp": "2026-06-17T10:28:00Z"},
                {"id": "err-3", "severity": "ERROR", "source": "a2a-bridge", "message": "Agent handshake failed", "timestamp": "2026-06-17T10:25:00Z"},
                {"id": "err-4", "severity": "WARN", "source": "state-machine", "message": "Transition timeout on VERIFY", "timestamp": "2026-06-17T10:20:00Z"},
                {"id": "err-5", "severity": "ERROR", "source": "cost-tracker", "message": "Budget exhausted for agent task-42", "timestamp": "2026-06-17T10:15:00Z"},
            ],
        }

    @app.get("/api/v1/observability/cost-report")
    def observability_cost_report(agent_id: str = "", since: str = "") -> dict[str, Any]:
        return _cost_tracker.get_cost_report(agent_id=agent_id or None, since=since or None)

    @app.get("/api/v1/observability/cost-by-team")
    def observability_cost_by_team() -> dict[str, Any]:
        return _cost_tracker.get_cost_by_team()

    @app.get("/api/v1/evolution/status")
    def evolution_status() -> dict[str, Any]:
        return {
            "running": False,
            "metrics_mode": "simulated",
            "real_writes_enabled": False,
            "proposal_execution": "dry_run_only",
        }

    @app.post("/api/v1/evolution/dry-run")
    def evolution_dry_run() -> dict[str, Any]:
        import asyncio

        from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine

        config = EvolutionConfig(dry_run=True, metrics_mode="simulated")
        result = asyncio.run(RecursiveEvolutionEngine(config).run())
        return {
            "dry_run": True,
            "real_writes_enabled": False,
            "stop_reason": result.stop_reason,
            "total_rounds": result.total_rounds,
            "all_passed": result.all_passed,
        }

    @app.post("/api/v1/evolution/approve-proposal")
    def evolution_approve_proposal(body: dict[str, Any]) -> dict[str, Any]:
        if body.get("approved") is not True or body.get("execute") is not True:
            raise HTTPException(
                status_code=403,
                detail="explicit approval and execute=true are required for proposal execution",
            )
        return {
            "proposal_id": body.get("proposal_id", ""),
            "accepted": True,
            "real_writes_enabled": False,
            "mode": "approval_recorded_only",
        }

    # ── Verifier & Consensus API ─────────────────────────────────────────
    from maref.integration.maref_loop_adapter import MAREFLoop

    _verifier_loop = MAREFLoop()

    @app.get("/api/verifiers")
    def list_verifiers() -> dict[str, Any]:
        return {"verifiers": _verifier_loop.get_verifiers()}

    @app.post("/api/verifiers/register")
    def register_verifier(body: dict[str, str]) -> dict[str, str]:
        _verifier_loop.register_verifier(
            name=body.get("name", ""),
            model=body.get("model", ""),
            methodology=body.get("methodology", ""),
        )
        return {"status": "registered"}

    @app.post("/api/verifiers/check")
    def verifier_check(body: dict[str, Any]) -> dict[str, Any]:
        result = _verifier_loop.check(
            action=body.get("action", ""),
            context=body.get("context", {}),
        )
        return {"result": result}

    @app.get("/api/verifiers/drift")
    def verifier_drift() -> dict[str, Any]:
        return {"drifted": _verifier_loop.detect_drift()}

    @app.get("/api/verifiers/history")
    def verifier_history() -> dict[str, Any]:
        return {"history": _verifier_loop.get_history()}


class SidecarFastAPI(FastAPI):
    def __init__(self, collector: ObservationCollector, monitor: CompositeMonitor, obs_bridge: ObsBridge | None = None, **kwargs: Any) -> None:
        super().__init__(title="MAREF Sidecar", version="0.35.0-beta")
        self.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.add_middleware(SecurityHeadersMiddleware)
        self.include_router(gaas_router)
        a2a_bridge = create_a2a_bridge()
        _signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
        self.include_router(create_a2a_router(a2a_bridge, signing_key=_signing_key))
        _setup_routes(self, collector, monitor, obs_bridge)


def create_app(collector: ObservationCollector, monitor: CompositeMonitor, obs_bridge: ObsBridge | None = None) -> FastAPI:
    app = FastAPI(title="MAREF Sidecar", version="0.35.0-beta")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(gaas_router)
    a2a_bridge = create_a2a_bridge()
    _signing_key = os.environ.get("MAREF_A2A_SIGNING_KEY")
    app.include_router(create_a2a_router(a2a_bridge, signing_key=_signing_key))
    _setup_routes(app, collector, monitor, obs_bridge)
    return app
