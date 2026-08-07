from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import A2A_PROTOCOL_VERSION, A2ATaskState
from maref.signing.signing_key import ReportSigningKey


def create_a2a_router(
    bridge: A2ABridge,
    signing_key: str | None = None,
    peer_public_keys: dict[str, str] | None = None,
) -> APIRouter:
    """Create the A2A HTTP router.

    v0.50 W3-S1 (I7): when ``peer_public_keys`` (``{agent_id: Ed25519 public key}``)
    is provided, ``tasks/send`` requests are verified against the sender's
    ``X-A2A-Signature`` / ``X-A2A-Timestamp`` headers. Requests from an
    unknown sender or with an invalid signature are rejected with 401.
    """
    if peer_public_keys is None:
        peer_public_keys = {}

    def _sign_card(card: dict[str, Any]) -> str:
        if signing_key is None:
            return ""
        key_bytes = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
        payload = json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(key_bytes, payload, hashlib.sha256).hexdigest()

    def _assert_circuit_closed() -> None:
        try:
            bridge._check_circuit_breaker()
        except CommunicationBlockedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def _verify_sender(request: Request, body: dict[str, Any]) -> bool:
        """Verify the sender's Ed25519 signature when peer keys are configured.

        Returns True when verification passes or no peer keys are configured.
        """
        if not peer_public_keys:
            return True
        agent_id = request.headers.get("X-A2A-Agent-Id", "")
        public_key = peer_public_keys.get(agent_id)
        if public_key is None:
            return False
        signature = request.headers.get("X-A2A-Signature", "")
        timestamp = request.headers.get("X-A2A-Timestamp", "")
        if not signature or not timestamp:
            return False
        body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        signed = f"{timestamp}.{body_bytes.decode('utf-8')}".encode()
        return ReportSigningKey.verify_signature(public_key, signature, signed)

    router = APIRouter()

    @router.post("/api/a2a/task/send")
    async def task_send(request: Request, body: dict[str, Any]) -> JSONResponse:
        try:
            if not _verify_sender(request, body):
                return JSONResponse(
                    status_code=401,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32001,
                            "message": "Unauthorized: sender signature verification failed",
                        },
                    },
                )
            if body.get("jsonrpc") != "2.0":
                return JSONResponse(
                    status_code=200,
                    content={
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                    },
                )

            method = body.get("method", "")
            req_id = body.get("id")

            if method != "tasks/send":
                return JSONResponse(
                    status_code=200,
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    },
                )

            _assert_circuit_closed()

            params = body.get("params", {})
            message = params.get("message", {})
            parts = message.get("parts", [])
            text = ""
            if parts and isinstance(parts, list) and len(parts) > 0:
                text = parts[0].get("text", "") or ""
            if not text:
                text = params.get("id", "") or ""

            metadata = params.get("metadata", {})
            requested_skills = metadata.get("skills", metadata.get("capabilities", []))
            if requested_skills:
                registered_ids = {cap.id for cap in bridge._capabilities}
                unknown = [s for s in requested_skills if s not in registered_ids]
                if unknown:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32602,
                                "message": f"Unknown skills: {', '.join(unknown)}",
                            },
                        },
                    )

            task_id = bridge.create_task(text, metadata)
            task = bridge.get_task(task_id)

            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "id": task_id,
                        "status": {"state": task.a2a_state.value if task else "submitted"},
                        "createdAt": task.created_at if task else time.time(),
                    },
                },
            )
        except HTTPException:
            raise
        except CommunicationBlockedError:
            return JSONResponse(
                status_code=503,
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": "Circuit breaker is OPEN"},
                },
            )
        except Exception:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": "Server error"},
                },
            )

    @router.get("/api/a2a/task/{task_id}")
    async def task_get(task_id: str) -> JSONResponse:
        try:
            _assert_circuit_closed()

            task = bridge.get_task(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")

            return JSONResponse(
                status_code=200,
                content={
                    "id": task.task_id,
                    "status": {"state": task.a2a_state.value},
                    "description": task.description,
                    "maref_state": task.maref_state.name,
                    "createdAt": task.created_at,
                    "updatedAt": task.updated_at,
                    "history": [
                        {"state": task.a2a_state.value, "timestamp": task.updated_at},
                    ],
                },
            )
        except HTTPException:
            raise
        except CommunicationBlockedError:
            return JSONResponse(
                status_code=503,
                content={"detail": "Circuit breaker is OPEN"},
            )
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"detail": "Server error"},
            )

    @router.post("/api/a2a/task/cancel")
    async def task_cancel(request: Request, body: dict[str, Any]) -> JSONResponse:
        try:
            if not _verify_sender(request, body):
                return JSONResponse(
                    status_code=401,
                    content={"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized: sender signature verification failed"}},
                )
            task_id = body.get("id") or body.get("task_id")
            if not task_id:
                return JSONResponse(status_code=400, content={"detail": "Missing task ID"})

            reason = body.get("reason", "")
            if not bridge.force_halt_task(task_id, reason):
                return JSONResponse(status_code=404, content={"detail": "Task not found"})

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "task_id": task_id,
                    "state": "canceled",
                    "reason": reason,
                },
            )
        except HTTPException:
            raise
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Server error"})

    @router.post("/api/a2a/task/state")
    async def task_state(request: Request, body: dict[str, Any]) -> JSONResponse:
        try:
            if not _verify_sender(request, body):
                return JSONResponse(
                    status_code=401,
                    content={"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized: sender signature verification failed"}},
                )
            task_id = body.get("task_id") or body.get("id")
            state = body.get("state", "")

            if not task_id or not state:
                return JSONResponse(status_code=400, content={"detail": "Missing task ID or state"})

            _assert_circuit_closed()

            if not bridge.sync_state_from_a2a(task_id, state):
                return JSONResponse(status_code=404, content={"detail": "Task not found"})

            return JSONResponse(
                status_code=200,
                content={"success": True, "state": state},
            )
        except HTTPException:
            raise
        except CommunicationBlockedError:
            return JSONResponse(
                status_code=503,
                content={"detail": "Circuit breaker is OPEN"},
            )
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Server error"})

    @router.get("/api/a2a/task/{task_id}/stream")
    async def task_stream(task_id: str) -> StreamingResponse:
        _assert_circuit_closed()
        task = bridge.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        async def event_stream() -> Any:
            yield "data: connected\n\n"
            while True:
                try:
                    state = await bridge.wait_for_state_change(task_id)
                except Exception:
                    break
                yield f"data: {state.value}\n\n"
                if state in (A2ATaskState.COMPLETED, A2ATaskState.CANCELED, A2ATaskState.FAILED):
                    yield "data: [DONE]\n\n"
                    break

        return StreamingResponse(
            event_stream(),
            headers={"content-type": "text/event-stream"},
        )

    @router.post("/api/a2a/task/push_notification")
    async def task_push_notification(request: Request, body: dict[str, Any]) -> JSONResponse:
        try:
            if not _verify_sender(request, body):
                return JSONResponse(
                    status_code=401,
                    content={"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized: sender signature verification failed"}},
                )
            task_id = body.get("task_id") or body.get("id", "")
            if not task_id:
                return JSONResponse(status_code=400, content={"detail": "Missing task ID"})
            event = body.get("event", {})
            bridge.handle_push_notification(task_id, event)
            return JSONResponse(status_code=200, content={"success": True, "task_id": task_id})
        except ValueError as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})
        except CommunicationBlockedError:
            return JSONResponse(
                status_code=503,
                content={"detail": "Circuit breaker is OPEN"},
            )
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Server error"})

    @router.post("/a2a/tasks")
    async def a2a_tasks_spec(request: Request, body: dict[str, Any]) -> JSONResponse:
        if not _verify_sender(request, body):
            return JSONResponse(
                status_code=401,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Unauthorized: sender signature verification failed",
                    },
                },
            )
        return await task_send(request, body)

    @router.get("/a2a/tasks/{task_id}")
    async def a2a_tasks_get_spec(task_id: str) -> JSONResponse:
        return await task_get(task_id)

    @router.get("/.well-known/agent-card.json")
    async def agent_card(request: Request) -> JSONResponse:
        try:
            _assert_circuit_closed()

            base_url = str(request.base_url).rstrip("/")
            card = bridge.build_agent_card(base_url)
            card["protocolVersion"] = A2A_PROTOCOL_VERSION

            signature = _sign_card(card)

            return JSONResponse(
                status_code=200,
                content={
                    "agentCard": card,
                    "signature": signature,
                    "signingAlgorithm": "hmac-sha256" if signing_key else "",
                },
                headers={"Cache-Control": "no-cache"},
            )
        except HTTPException:
            raise
        except CommunicationBlockedError as exc:
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
            )
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Server error"})

    return router
