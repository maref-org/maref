# MAREF — Agent Governance OS

**M**ulti-**A**gent **R**ecursive **E**ngineering **F**ramework

[![CI](https://github.com/maref-org/maref/actions/workflows/ci.yml/badge.svg)](https://github.com/maref-org/maref/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.30.0--GA-blue)](https://github.com/maref-org/maref/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-pending-b31b1b.svg)](https://arxiv.org/)

MAREF is an open-source governance layer for multi-agent systems. It focuses on the parts most agent frameworks leave underspecified: lifecycle control, safety boundaries, trust, drift detection, auditability, and recursive improvement.

Most agent frameworks help agents act. MAREF helps agent systems stay governable.

## Why MAREF?

Multi-agent systems are moving from demos to infrastructure. Once agents can spawn tools, coordinate tasks, access desktops, call APIs, and modify state, orchestration alone is not enough.

MAREF provides a governance operating layer for:

- Safety decisions before actions are executed
- Formalized state transitions for agent lifecycle control
- Trust and identity boundaries across agents and protocols
- Drift detection for models, behaviors, and system state
- Auditable execution for human-in-the-loop and policy review
- Recursive improvement loops that remain bounded by governance rules

## Who is it for?

MAREF is designed for:

- Researchers studying multi-agent systems, agent governance, and formal verification
- Builders integrating LangGraph, AutoGen, CrewAI, MCP, A2A, or custom agent stacks
- Teams deploying desktop or browser agents that need safety boundaries
- Organizations evaluating agent risk, auditability, and policy enforcement
- Developers building open agent infrastructure rather than one-off assistants

## Core Capabilities

### Governance Layer

- **Gray-code governance state machine** for stable, low-distance state transitions
- **TLA+ formal verification** for safety and convergence properties
- **Circuit breaker control** with lockout and recovery states
- **Four-level safety decision tree**: Rule → Mode → SafetyGate → User
- **Trust boundary management** for cross-agent and cross-domain calls
- **Audit trail support** for reviewable, tamper-aware execution records

### Agent Operations Layer

- Desktop-agent control loop: screenshot → parse → act → verify
- Multi-agent task decomposition and scheduling
- Isolated sub-agent execution contexts
- Browser automation with safety boundaries
- Mobile-to-desktop task bridge patterns

### Evolution Layer

- Recursive observation → optimization → convergence loop
- Red-team / blue-team adversarial evaluation patterns
- Chaos engineering for LLM and agent failures
- Memory layering for hot, warm, and cold knowledge
- Trust scoring with anti-Goodhart considerations

### Ecosystem Layer

- MCP and A2A protocol integration points
- Adapters for agent frameworks and external tools
- OpenTelemetry-compatible observability path
- Python core with TypeScript SDK direction
- Apache-2.0 licensing and contribution workflow

## Architecture

```text
                    MAREF: Agent Governance OS
    ┌─────────────────────────────────────────────────────────┐
    │  Application Layer                                      │
    │  LangGraph / CrewAI / AutoGen / custom agent systems    │
    │  ─────────────────────────────────────────────────────  │
    │  Governance Layer                                       │
    │  State machine · Safety gate · Trust · Audit · Drift    │
    │  ─────────────────────────────────────────────────────  │
    │  Protocol Layer                                         │
    │  MCP · A2A · APIs · desktop/browser control surfaces    │
    └─────────────────────────────────────────────────────────┘
```

## Quick Start

### From source

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Basic governance overlay

```python
from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceState

overlay = GovernanceOverlay()
overlay._state_machine.transition(GovernanceState.OBSERVE)
overlay._state_machine.transition(GovernanceState.ANALYZE)
print(overlay.get_status())
```

### Common commands

```bash
maref --help
maref status
maref serve --port 8000 --gui
pytest tests/ -v
```

## Documentation

- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
- [Contributor License Agreement](CLA.md)
- [Security whitepaper](docs/MAREF-Security-Whitepaper.md)
- [Technical whitepaper draft](docs/MAREF-Technical-Whitepaper-arXiv.md)
- [Release checklist](docs/github-release-checklist-v0.30.0-GA.md)

## Project Status

MAREF is currently in an early open-source release phase.

| Area | Status |
|---|---|
| Repository | Public |
| License | Apache-2.0 |
| Release | v0.30.0-GA tag available |
| arXiv whitepaper | Pending endorsement / ID |
| Security policy | Available |
| CLA | Available |
| Contribution workflow | Available |

## Roadmap

- [x] Governance state machine and safety boundary foundations
- [x] Formal verification and audit-oriented architecture
- [x] Desktop-agent and protocol integration experiments
- [x] v0.30.0-GA open-source preparation
- [ ] arXiv whitepaper ID and README badge update
- [ ] Public issue roadmap and good-first-issue queue
- [ ] PyPI package publication and installation verification
- [ ] Governance examples for LangGraph / AutoGen / MCP / A2A
- [ ] Community contribution and CLA automation

## Contributing

We welcome contributions in governance, safety, protocol integration, observability, testing, and documentation.

Start here:

1. Read [CONTRIBUTING.md](CONTRIBUTING.md)
2. Read [SECURITY.md](SECURITY.md) before reporting vulnerabilities
3. Open an issue or discussion before large architectural changes
4. Sign the CLA when submitting pull requests

## Security

Do not open public issues for vulnerabilities. Follow the process in [SECURITY.md](SECURITY.md).

MAREF includes cryptographic and safety-related components. Users are responsible for their own compliance review before production deployment.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

## 中文摘要

MAREF（Multi-Agent Recursive Engineering Framework）是一个面向多智能体系统的开源治理层框架。它关注的不只是“让 Agent 执行任务”，而是让 Agent 系统在执行过程中保持可治理、可审计、可约束、可演化。

MAREF 的核心定位是 **Agent Governance OS**：管理多 Agent 系统的生命周期、安全边界、信任关系、漂移风险、审计记录和递归改进过程。

适用场景包括：

- 多智能体系统研究
- Agent 安全与治理实验
- 桌面 / 浏览器 Agent 的安全执行边界
- MCP / A2A / LangGraph / AutoGen / CrewAI 等生态集成
- 企业或研究机构的 Agent 风险评估与审计

当前仓库已公开，采用 Apache-2.0 协议。arXiv 白皮书正在等待 cs.MA 背书和正式 ID，获得 ID 后将更新 README 顶部 badge 与引用信息。
