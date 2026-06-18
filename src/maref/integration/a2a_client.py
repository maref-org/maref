from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

AGENT_ID = "maref-agent"


class A2AClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._active_tasks: dict[str, dict[str, Any]] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-A2A-Agent-Id": AGENT_ID,
        }

    async def send_task(
        self,
        agent_url: str,
        skill_id: str,
        input_data: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            req_id = str(uuid.uuid4())
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tasks/send",
                "params": {
                    "id": req_id,
                    "message": {
                        "parts": [{"text": input_data}],
                    },
                    "metadata": {
                        "skills": [skill_id],
                        **(metadata or {}),
                    },
                },
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{agent_url.rstrip('/')}/api/a2a/task/send",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                result = resp.json()
                task_id = result.get("result", {}).get("id", "")
                if task_id:
                    self._active_tasks[task_id] = {
                        "agent_url": agent_url,
                        "created_at": time.time(),
                        "status": result.get("result", {}).get("status", {}),
                    }
                return result
        except Exception:
            return None

    async def get_task(self, agent_url: str, task_id: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{agent_url.rstrip('/')}/api/a2a/task/{task_id}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def cancel_task(self, agent_url: str, task_id: str, reason: str = "") -> bool:
        try:
            payload = {
                "id": task_id,
                "task_id": task_id,
                "reason": reason,
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{agent_url.rstrip('/')}/api/a2a/task/cancel",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                success = data.get("success", False)
                if success and task_id in self._active_tasks:
                    self._active_tasks.pop(task_id, None)
                return success
        except Exception:
            return False

    async def push_state(
        self, agent_url: str, task_id: str, state: str
    ) -> bool:
        try:
            payload = {
                "task_id": task_id,
                "id": task_id,
                "state": state,
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{agent_url.rstrip('/')}/api/a2a/task/state",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("success", False)
        except Exception:
            return False

    async def discover_agent_card(self, agent_url: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{agent_url.rstrip('/')}/.well-known/agent-card.json",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    def get_active_tasks(self) -> dict[str, dict[str, Any]]:
        return dict(self._active_tasks)

    async def subscribe(
        self, agent_url: str, task_id: str, callback: Callable[[str], Any]
    ) -> None:
        try:
            async with httpx.AsyncClient(timeout=None) as client, client.stream(
                "GET",
                f"{agent_url.rstrip('/')}/api/a2a/task/{task_id}/stream",
                headers=self._headers(),
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data in ("connected", "[DONE]"):
                            continue
                        await callback(data)
        except Exception:
            pass

    def clear_active_tasks(self) -> None:
        self._active_tasks.clear()
