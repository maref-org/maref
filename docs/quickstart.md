# MAREF Quickstart Guide

**5 minutes to your first governed multi-agent system.**

---

## 1. Installation

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 -m venv .venv
source .venv/bin/activate

# Core framework
pip install -e ".[dev]"

# With desktop agent support (macOS recommended)
pip install -e ".[dev,desktop]"

# With ML support (for OmniParser real backend)
pip install -e ".[dev,desktop,ml]"
```

Verify installation:

```bash
maref --help
maref status
```

---

## 2. Quick Tour

### 2.1 Governance Status

```bash
maref status                    # Table view
maref status --verbose          # JSON view
```

### 2.2 Observe State Transitions

```bash
maref observe --count 5
maref observe --interval 0.5 --count 20
```

### 2.3 Analyze State Machine

```bash
maref analyze --state DECIDE
maref analyze --state HALT --graph
```

### 2.4 Desktop Agent (Dry-run)

```bash
# Demo (safe, no real clicks)
maref desktop demo

# Run a task (dry-run by default)
maref desktop run --task "open Finder"
```

For live execution (requires macOS Accessibility permissions):

```bash
# Grant permissions first:
# System Preferences → Privacy & Security → Accessibility → add Terminal

maref desktop run --task "open Finder" --live
```

### 2.5 Audit Log

```bash
maref audit show
maref audit show --last 50
maref audit show --type circuit_breaker
```

### 2.6 Trust Engine

```bash
maref trust score --agent agent-1
maref trust score
```

### 2.7 Governance Controls

```bash
maref governance status
```

### 2.8 Drift Detection

```bash
maref drift check
maref drift check --model qwen
```

### 2.9 Serve (HTTP API)

```bash
maref serve --port 8000

# Endpoints:
# http://localhost:8000/health    — Health check
# http://localhost:8000/agents    — Agent states
# http://localhost:8000/metrics   — Prometheus metrics
```

### 2.10 MCP Integration + Sidecar Start

```bash
# Start sidecar + auto-register MCP tools with opencode
maref start --port 8000

# With GUI dashboard
maref start --port 8000 --gui
```

The `start` command writes/checks `opencode.json` so opencode discovers MAREF's MCP tools on launch. Available MCP tools:

| Tool | Description |
|------|-------------|
| `maref_status` | Governance state machine status |
| `maref_audit_log` | Query audit log entries |
| `maref_circuit_breaker` | Circuit breaker states |
| `maref_trust_score` | Agent trust scores |
| `maref_drift_check` | Distribution drift detection |
| `maref_health` | Sidecar health check |

MCP endpoint: `POST /api/mcp` (JSON-RPC), capabilities at `GET /api/mcp/.well-known`.

---

## 4. Integrate with Existing Agent Frameworks

### 4.1 AutoGen

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision

# Create your AutoGen team
team = RoundRobinGroupChat(agents=[agent1, agent2])

# Wrap with MAREF observation + governance
adapter = AutoGenAdapter(team)

# Observe the stream with automatic safety checks
async for msg in adapter.observe_stream(team.run_stream(task="...")):
    # MAREF records every message for audit
    if isinstance(msg, TaskResult):
        break

# Inject governance decision
msg = {"content": "rm -rf /important"}
msg = adapter.inject_governance(msg, GovernanceDecision.BLOCK, "destructive command")
```

### 4.2 CrewAI

```python
from crewai import Crew, Agent, Task
from sidecar.adapters.crewai import CrewAIAdapter

crew = Crew(agents=[agent], tasks=[task])
adapter = CrewAIAdapter(crew)

# Check task safety before execution
decision, reason = adapter.evaluate_task_safety(task.description)
if decision == "block":
    print(f"Task blocked: {reason}")
else:
    task = adapter.inject_governance(task, decision, reason)
    crew.kickoff()

# Observe after execution
adapter.observe_agent_activity(agent.role, task.description)
state = await adapter.get_state(AgentId(name=agent.role, namespace="crewai"))
```

### 4.3 LangGraph

```python
from langgraph.graph import StateGraph
from sidecar.adapters.langgraph import LangGraphAdapter

graph = StateGraph(MyState)
graph.add_node("process", process_node)
graph.add_edge("process", "human_review")

adapter = LangGraphAdapter(graph)

# Check transition safety between nodes
decision, reason = adapter.evaluate_node_safety("human_review", current_state)
if decision == "block":
    print(f"Transition blocked: {reason}")
else:
    adapter.observe_transition("human_review", from_state="process")
    state = adapter.inject_governance("human_review", current_state, decision, reason)
```

---

## 5. Environment Diagnostic

```bash
python scripts/check_desktop_env.py
```

Checks: dependencies → macOS permissions → window manager → input controller → screen parser → desktop agent.

---

## 6. Next Steps

- Read the [Security Whitepaper](docs/MAREF-Security-Whitepaper.md)
- Run `pytest tests/ -v` for the full test suite
- Explore `src/formal/MAREFDeskJoint.tla` for TLA+ verification
- Join the community at [github.com/maref-org](https://github.com/maref-org)

---

## 7. Common Issues

| Problem | Solution |
|---------|----------|
| `ImportError: No module named 'PIL'` | `pip install Pillow` |
| `ImportError: No module named 'pyautogui'` | `pip install PyAutoGUI` |
| macOS Accessibility denied | System Preferences → Privacy & Security → Accessibility |
| `RuntimeError: OmniParserInterface not initialized` | Model not downloaded; use `backend="mock"` |
| `pyautogui.FailSafeException` | Mouse moved to corner (safety feature); re-run task |
