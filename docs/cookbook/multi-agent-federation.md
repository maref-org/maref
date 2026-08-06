# Cookbook: Multi-Agent A2A Federation

This guide covers setting up A2A federation across multiple agents with service discovery, task delegation, and cross-agent trust.

## Scenario

You have three agents (Analyst, Researcher, Writer) that need to collaborate. Analyst discovers Researcher, delegates a research task, and Writer compiles results — all under MAREF governance.

## Prerequisites

```bash
pip install maref httpx uvicorn fastapi
```

## Step 1: Heartbeat Registry

```python
"""registry.py — Central agent discovery service."""
from fastapi import FastAPI
from maref.integration.a2a_discovery import A2ADiscovery

app = FastAPI(title="Agent Registry")
discovery = A2ADiscovery(health_check_interval=30.0)


@app.post("/a2a/register")
def register(data: dict):
    discovery.register_agent(
        agent_id=data["agent_id"],
        agent_url=data["agent_url"],
        capabilities=data.get("capabilities", []),
    )
    return {"status": "registered"}


@app.get("/a2a/agents")
def list_agents():
    return {"agents": discovery.list_agents()}


@app.get("/a2a/discover")
def discover(capability: str = ""):
    return {"agents": discovery.discover_by_capability(capability)}
```

## Step 2: Federation Agent Template

```python
"""federation_agent.py — Template for federated agents."""
from fastapi import FastAPI
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_server import create_a2a_router
from maref.integration.a2a_client import A2AClient


def create_federated_agent(name: str, port: int, registry_url: str) -> FastAPI:
    sm = GovernanceStateMachine()
    audit = AuditLogger(hmac_key=f"{name}-key")
    cb = CircuitBreaker()
    bridge = A2ABridge(sm, audit, cb, agent_name=name)

    app = FastAPI(title=name)
    app.include_router(create_a2a_router(bridge, signing_key=f"{name}-sign-key"))

    @app.on_event("startup")
    async def register():
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(f"{registry_url}/a2a/register", json={
                "agent_id": name,
                "agent_url": f"http://localhost:{port}",
                "capabilities": ["maref-governance", "maref-delegate", "maref-audit"],
            })

    @app.get("/api/health")
    def health():
        return {"agent": name, "tasks": len(bridge.list_governed_tasks())}

    return app
```

## Step 3: Deploy Federated Agents

```python
"""deploy_federation.py"""
import uvicorn
from federation_agent import create_federated_agent

REGISTRY_URL = "http://localhost:9000"

analyst = create_federated_agent("analyst", 8001, REGISTRY_URL)
researcher = create_federated_agent("researcher", 8002, REGISTRY_URL)
writer = create_federated_agent("writer", 8003, REGISTRY_URL)

# Run in separate processes
uvicorn.run(analyst, port=8001)  # Terminal 1
uvicorn.run(researcher, port=8002)  # Terminal 2
uvicorn.run(writer, port=8003)  # Terminal 3
```

## Step 4: Delegate Across Federation

```python
"""client.py — Analyst delegates to Researcher."""
import asyncio
from maref.integration.a2a_client import A2AClient

async def main():
    client = A2AClient(timeout=30.0)

    card = await client.discover_agent_card("http://localhost:8002")
    print(f"Discovered: {card['agentCard']['name']}")

    result = await client.send_task(
        agent_url="http://localhost:8002",
        skill_id="maref-delegate",
        input_data="Research quantum computing trends",
        metadata={"priority": "high", "source": "analyst"},
    )
    task_id = result["id"]
    print(f"Task delegated: {task_id}")

    for _ in range(15):
        status = await client.get_task("http://localhost:8002", task_id)
        state = status.get("status", {}).get("state", "")
        print(f"  State: {state}")
        if state in ("completed", "failed", "canceled"):
            break
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 5: Verify

```python
import httpx

resp = httpx.get("http://localhost:9000/a2a/agents")
agents = resp.json()["agents"]
print(f"Registered agents: {[a['agent_id'] for a in agents]}")

resp = httpx.get("http://localhost:8001/api/health")
print(f"Analyst: {resp.json()}")

resp = httpx.get("http://localhost:8002/api/health")
print(f"Researcher: {resp.json()}")
```
