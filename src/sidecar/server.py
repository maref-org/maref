from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from maref.observability.security_headers_middleware import SecurityHeadersMiddleware

# ── Optional routers ────────────────────────────────────────────────────
try:
    from sidecar.gaas_router import router as gaas_router
except Exception:
    gaas_router = None

logger = logging.getLogger(__name__)

# ── In-memory stores for fallback routes ────────────────────────────────
_sessions: dict[str, dict] = {}
_messages: dict[str, list[dict]] = {}
_providers = [
    {"id": "openai", "name": "OpenAI", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    {"id": "anthropic", "name": "Anthropic", "models": ["claude-3-5-sonnet", "claude-3-opus"]},
    {"id": "google", "name": "Google", "models": ["gemini-1.5-pro", "gemini-1.5-flash"]},
]
_skills = [
    {"id": "web_search", "name": "Web Search", "description": "Search the web for information"},
    {"id": "code_execution", "name": "Code Execution", "description": "Execute Python/Node.js code"},
    {"id": "file_operations", "name": "File Operations", "description": "Read, write, and manage files"},
]
_tasks: dict[str, dict] = {}


def _register_session_routes(app: FastAPI) -> None:
    """Register session management routes."""

    @app.get("/api/sessions")
    async def list_sessions():
        return {"sessions": list(_sessions.values())}

    @app.post("/api/sessions")
    async def create_session(body: dict):
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "title": body.get("title", "New Session"),
            "mode": body.get("mode", "chat"),
            "provider": body.get("provider", "openai"),
            "model": body.get("model", "gpt-4o"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        _sessions[session_id] = session
        _messages[session_id] = []
        return session

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')
        return _sessions[session_id]

    @app.get("/api/sessions/{session_id}/messages")
    async def list_messages(session_id: str):
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')
        return {"messages": _messages.get(session_id, [])}

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: dict):
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')

        user_msg = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": body.get("content", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _messages[session_id].append(user_msg)

        # Simulate assistant response (fallback)
        assistant_msg = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": f"收到消息: {body.get('content', '')}（当前为降级模式，无真实 LLM 响应）",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _messages[session_id].append(assistant_msg)

        return assistant_msg

    @app.post("/api/sessions/{session_id}/interrupt")
    async def interrupt_session(session_id: str):
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')
        _sessions[session_id]["status"] = "interrupted"
        return {"status": "ok"}

    @app.post("/api/sessions/{session_id}/approve")
    async def approve_action(session_id: str, body: dict):
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')
        return {"status": "ok", "action_id": body.get("actionId")}

    @app.get("/api/sessions/{session_id}/stream")
    async def stream_session(session_id: str):
        """SSE stream for real-time messages."""
        if session_id not in _sessions:
            return Response(status_code=404, content='{"message":"Session not found"}')

        async def event_generator():
            msg_index = 0
            while True:
                msgs = _messages.get(session_id, [])
                if msg_index < len(msgs):
                    msg = msgs[msg_index]
                    yield f"data: {json.dumps(msg)}\n\n"
                    msg_index += 1
                await asyncio.sleep(0.5)

        return StreamingResponse(event_generator(), media_type="text/event-stream")


def _register_chat_routes(app: FastAPI) -> None:
    """Register /chat shortcut endpoint."""

    @app.get("/chat")
    async def chat_page():
        return Response(
            content="""<!DOCTYPE html>
<html>
<head><title>Chat</title></head>
<body>
<h1>MAREF Chat</h1>
<p>Quick chat endpoint — use <code>/api/sessions</code> for full API.</p>
</body>
</html>""",
            media_type="text/html",
        )


def _register_provider_routes(app: FastAPI) -> None:
    """Register provider and skill routes."""

    @app.get("/api/providers")
    async def get_providers():
        return {"providers": _providers}

    @app.get("/api/skills")
    async def get_skills():
        return {"skills": _skills}


def _register_task_routes(app: FastAPI) -> None:
    """Register task management routes."""

    @app.get("/api/tasks")
    async def list_tasks():
        return {"tasks": list(_tasks.values())}

    @app.post("/api/v1/tasks")
    async def create_task(body: dict):
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "name": body.get("name", "Unnamed Task"),
            "description": body.get("description", ""),
            "priority": body.get("priority", 0),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": body.get("payload", {}),
            "session_id": body.get("session_id"),
            "tags": body.get("tags", []),
            "timeout_seconds": body.get("timeout_seconds", 300),
            "max_retries": body.get("max_retries", 3),
        }
        _tasks[task_id] = task
        return task

    @app.get("/api/v1/tasks/{task_id}")
    async def get_task(task_id: str):
        if task_id not in _tasks:
            return Response(status_code=404, content='{"message":"Task not found"}')
        return _tasks[task_id]

    @app.post("/api/v1/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        if task_id not in _tasks:
            return Response(status_code=404, content='{"message":"Task not found"}')
        _tasks[task_id]["status"] = "cancelled"
        return _tasks[task_id]

    @app.get("/api/v1/tasks")
    async def list_tasks_v1(
        status: str | None = None,
        priority: int | None = None,
        session_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        tasks = list(_tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        if priority is not None:
            tasks = [t for t in tasks if t["priority"] == priority]
        if session_id:
            tasks = [t for t in tasks if t.get("session_id") == session_id]
        if tag:
            tasks = [t for t in tasks if tag in t.get("tags", [])]
        total = len(tasks)
        tasks = tasks[offset : offset + limit]
        return {"tasks": tasks, "total": total}


def _register_filetree_route(app: FastAPI) -> None:
    """Register file tree route."""

    @app.get("/api/filetree")
    async def get_filetree():
        return {"tree": []}


def _register_placeholder_routes(app: FastAPI) -> None:
    """Register placeholder routes for unimplemented endpoints."""

    placeholder_paths = [
        "/v1/desktop/status",
        "/v1/desktop/permissions",
        "/v1/desktop/calibrate",
        "/v1/desktop/capture",
        "/v1/desktop/parse",
        "/v1/desktop/ui-elements",
        "/v1/desktop/execute",
        "/v1/desktop/execute-plan",
        "/v1/desktop/execute-template",
        "/v1/desktop/history",
        "/v1/desktop/history/{execution_id}",
        "/v1/desktop/policy-status",
        "/v1/desktop/set-mode",
        "/v1/desktop/hitl/approve",
        "/v1/desktop/hitl/reject",
        "/v1/desktop/decision-log",
        "/v1/desktop/governance-status",
        "/v1/desktop/governance/mode",
        "/v1/desktop/governance-events",
        "/v1/hitl/request",
        "/v1/hitl/confirm",
        "/v1/hitl/cancel",
        "/v1/hitl/pause",
        "/v1/hitl/resume",
        "/v1/hitl/pending",
        "/v1/hitl/stats",
        "/v1/hitl/{event_id}/approve",
        "/v1/hitl/{event_id}/deny",
        "/v1/hitl/history",
    ]

    for path in placeholder_paths:
        async def placeholder():
            return {"message": "Not implemented — requires full MAREF agent service"}
        app.add_api_route(f"/api/{path.lstrip('/')}", placeholder, methods=["GET", "POST"])


def create_app(obs_bridge: Any = None) -> FastAPI:
    app = FastAPI(
        title="MAREF Sidecar",
        version="0.30.0-GA",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SecurityHeadersMiddleware)

    # ── GaaS router (if available) ──────────────────────────────────
    if gaas_router is not None:
        app.include_router(gaas_router)
        logger.info("GaaS router mounted successfully")
    else:
        logger.warning("Using fallback GaaS Routes — full GaaS service unavailable")

    # ── Health & Metrics ────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.30.0-GA"}

    @app.get("/metrics")
    async def metrics():
        prometheus_text = "# MAREF Sidecar metrics\n"
        return Response(content=prometheus_text, media_type="text/plain; version=0.0.4")

    # ── Register fallback routes ────────────────────────────────────
    _register_session_routes(app)
    _register_chat_routes(app)
    _register_provider_routes(app)
    _register_task_routes(app)
    _register_filetree_route(app)
    _register_placeholder_routes(app)

    logger.info("All fallback routes registered")

    return app
