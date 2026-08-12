from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


class A2ADiscovery:
    def __init__(self, health_check_interval: float = 60.0) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._health_check_interval = health_check_interval
        self._bg_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def register_agent(
        self,
        agent_id: str,
        agent_url: str,
        capabilities: list[str] | None = None,
    ) -> None:
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "agent_url": agent_url.rstrip("/"),
            "capabilities": capabilities or [],
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
            "healthy": True,
        }

    def unregister_agent(self, agent_id: str) -> bool:
        return self._agents.pop(agent_id, None) is not None

    def discover_agents(self, capability_filter: str | None = None) -> list[dict[str, Any]]:
        if capability_filter is None:
            return list(self._agents.values())
        return [
            agent for agent in self._agents.values() if capability_filter in agent["capabilities"]
        ]

    async def health_check(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{agent['agent_url']}/api/health",
                )
                healthy = resp.status_code == 200
        except Exception:
            healthy = False
        agent["healthy"] = healthy
        if healthy:
            agent["last_heartbeat"] = time.time()
        return healthy

    async def refresh_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for agent_id in list(self._agents.keys()):
            results[agent_id] = await self.health_check(agent_id)
        return results

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        return list(self._agents.values())

    async def start_background_health_checks(self) -> None:
        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._health_check_interval)
                await self.refresh_all()

        self._bg_task = asyncio.create_task(_loop())

    async def stop_background_health_checks(self) -> None:
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None
