# MAREF — Agent Governance OS

**M**ulti-**A**gent **R**ecursive **E**ngineering **F**ramework

<p align="center">
  <a href="https://github.com/maref-org/maref/stargazers"><img src="https://img.shields.io/github/stars/maref-org/maref?style=for-the-badge&logo=github&color=gold" alt="Stars"></a>
  <a href="https://github.com/maref-org/maref/network/members"><img src="https://img.shields.io/github/forks/maref-org/maref?style=for-the-badge&logo=github&color=blue" alt="Forks"></a>
  <a href="https://github.com/maref-org/maref/graphs/contributors"><img src="https://img.shields.io/github/contributors/maref-org/maref?style=for-the-badge&logo=github&color=green" alt="Contributors"></a>
  <a href="https://github.com/maref-org/maref/discussions"><img src="https://img.shields.io/github/discussions/maref-org/maref?style=for-the-badge&logo=github&color=purple" alt="Discussions"></a>
  <a href="https://github.com/maref-org/maref/releases"><img src="https://img.shields.io/github/v/release/maref-org/maref?style=for-the-badge&logo=github&color=red" alt="Release"></a>
</p>

> **The world's only framework positioning "Agent Governance" as its core product value.** Outperforms all competitors in governance depth (10/10 vs 0-3), treating agent governance as an independent value proposition rather than a security feature.

MAREF is the operating system kernel for the Agent world — managing the lifecycle, security boundaries, health, and evolutionary direction of agent clusters.

[中文版](README.zh-CN.md)

---

## Star History

![Star History](https://api.star-history.com/svg?repos=maref-org/maref&type=Date)

---

## Core Capabilities

### Governance Layer (World-Leading)
- **Three Loop Meta-Patterns** — Convergent / Exploratory / Interactive template library 🚧 (v0.36.0-rc)
- **10-State Gray Code Governance State Machine** — Mathematically provable convergence (6-bit, Hamming distance=1)
- **TLA+ Formal Verification** — 5 theorem proofs (Lyapunov convergence + Sperner completeness)
- **CircuitBreaker** — Auto-lock after 3 consecutive failures + HALT absorb state + 30s cooldown
- **Four-Tier Security Decision Tree** — Rule→Mode→SafetyGate→User, 97% automation rate
- **LoRA/Ontology Dual Drift Detection** — KL/JS/Hellinger triple divergence + human arbitration
- **Verifier Cross-Validation** — VerifierRegistry + VerifierConsensus (weighted majority / unanimous)
- **MAREFLoop Adapter** — Connect any Loop to MAREF governance in 5 lines of code

<p align="center">
  <img src="docs/assets/gray-code-fsm.svg" alt="Gray Code Governance State Machine — 10-state cyclic FSM with Hamming distance=1" width="800">
</p>

### Operations Layer
- **Desktop Agent Control** — Screenshot→Parse→Keyboard/Mouse→Verify full闭环 (macOS/Linux/Windows)
- **Multi-Agent Task Orchestration** — TaskDAG decomposition + 5D agent distribution + Saga compensation transactions
- **SubAgent Context Isolation** — Git Worktree-style, 96% token savings
- **Mobile→Desktop Task Bridging** — mDNS discovery + idempotent task queue + SSE push
- **Secure Browser Control** — Playwright + secure domain whitelist + authenticated session management

### Evolution Layer
- **Recursive Self-Evolution Engine** — C1(Observe)→C2(Optimize)→C3(Converge) triple loop
- **Red-Blue Teaming** — 200 rounds, 5 phases, attack intensity 2.47→18.98 (7.7×)
- **Chaos Engineering** — 5 types of LLM fault injection (latency/error/truncation/hallucination/timeout)
- **Three-Temperature Memory Framework** — Hot/Warm/Cold three-tier memory architecture
- **Trust Engine v2** — 5-factor weighting + Goodhart anti-strategic manipulation detection

### Ecosystem Layer
- **A2A/MCP Dual Protocol** — A2A v0.3 + MCP 6 transports
- **Cross-Framework Adapters** — AutoGen/CrewAI/LangGraph/Dify/Coze production-grade
- **OpenTelemetry** — Prometheus + Grafana + OTLP full-link observability
- **Serverless Runtime** — Lambda / Cloud Run ready
- **TypeScript SDK** — `@maref/sdk` npm package

---

## Quick Start

### 5-Minute Guide

```bash
# 1. Install MAREF
pip install maref

# 2. Run environment diagnostics (15 checks)
python scripts/check_desktop_env.py

# 3. Launch desktop agent demo (safe dry-run mode)
maref desktop demo

# 4. Start Sidecar service
maref serve --port 8000

# 5. Open GUI
open http://localhost:8000
```

### Quick Start Examples

**Option 1: CLI Mode**
```bash
# One-click install
pip install maref

# Query governance state
maref status

# Desktop agent demo
maref desktop demo

# Start service
maref serve --port 8000 --gui
```

**Option 2: Python API**
```python
from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceState

overlay = GovernanceOverlay()
overlay._state_machine.transition(GovernanceState.OBSERVE)
overlay._state_machine.transition(GovernanceState.ANALYZE)
print(overlay.get_status())

# --- Loop Engineering (v0.36.0-rc) ---

from maref.loop.convergent import ConvergentLoop
from maref.loop.exploratory import ExploratoryLoop
from maref.loop.interactive import InteractiveLoop
from maref.loop.bridge import LoopGovernanceBridge

async def example():
    loop = ConvergentLoop(
        solve_fn=lambda x: {"score": 0.95, "output": x},
        max_rounds=10,
    )
    bridge = LoopGovernanceBridge()
    result = await bridge.run_governed(loop, "example input")
    print(result.stop_reason, result.rounds_completed)
```

**Option 3: Full Project Example**
```bash
# Clone repository
git clone https://github.com/maref-org/maref.git
cd maref

# Create virtual environment with uv (recommended)
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[all]"

# Run tests
pytest tests/ -v --tb=short

# Launch full demo
python examples/simple_integration_demo.py
```

### FAQ

| Issue | Solution |
|-------|----------|
| Installation fails | Run `pip install --upgrade pip` and retry |
| Desktop control permission denied | Grant accessibility permissions in system settings |
| Port already in use | Use `--port` to specify an alternative port |
| Dependency conflict | Use `uv venv` to create an isolated environment |

---

## Architecture

```
                  MAREF: Agent Governance OS
    ┌─────────────────────────────────────────────────────────┐
    │  Application Layer ─── LangGraph / CrewAI / AutoGen     │
    │              / Anthropic (Orchestration/Control/Dev)     │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  Governance Layer ─── MAREF (This Framework)             │
    │             · State Machine · Circuit Breaker            │
    │             · 4-Tier Decision Tree · Identity/Trust      │
    │             · Drift Detection · Formal Verification       │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  Communication Layer ─── A2A / MCP (Google/Anthropic)    │
    └─────────────────────────────────────────────────────────┘
```

---

## Competitive Analysis

| Dimension | **MAREF** | Anthropic | OpenAI | LangGraph | CrewAI | AutoGen |
|-----------|-----------|-----------|--------|-----------|--------|---------|
| Governance/Security | **10** | 4 | 3 | 2 | 1 | 1 |
| Loop Integration (Verifier×Governance) | **10** | 6 | 0 | 0 | 0 | 0 |
| Loop Meta-Pattern Templates | ✅ v36 | 0 | 0 | 0 | 0 | 0 |
| Formal Verification | **10** | 0 | 0 | 0 | 0 | 0 |
| Drift Detection | **9** | 0 | 0 | 0 | 0 | 0 |
| Desktop Control | 8 | **9** | 7 | 0 | 0 | 0 |
| Orchestration | 7 | 8 | 8 | **9** | 8 | 8 |
| Identity/Trust | **7** | 0 | 0 | 0 | 0 | 0 |
| Community/Ecosystem | 3 | 8 | **9** | 8 | **9** | 8 |

---

## Contributors

<a href="https://github.com/maref-org/maref/graphs/contributors">
  <img src="https://contributors-img.web.app/image?repo=maref-org/maref" alt="Contributors" width="600">
</a>

---

## Latest Release

<!-- MAREF_RELEASE_START -->
<!-- MAREF_RELEASE_END -->

---

## Health

| Metric | Status |
|--------|--------|
| **CI** | [![CI](https://github.com/maref-org/maref/actions/workflows/ci.yml/badge.svg)](https://github.com/maref-org/maref/actions) |
| **Tests** | 4,300+ — [![Tests](https://img.shields.io/badge/tests-4300+-brightgreen.svg)]() |
| **Coverage** | 82% — [![Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen.svg)]() |
| **CodeQL** | [![CodeQL](https://github.com/maref-org/maref/actions/workflows/codeql.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/codeql.yml) |
| **Security** | [![Security Scan](https://github.com/maref-org/maref/actions/workflows/security-scan.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/security-scan.yml) |
| **SonarCloud** | [![SonarCloud](https://github.com/maref-org/maref/actions/workflows/sonarcloud.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/sonarcloud.yml) |
| **Python** | ![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg) |
| **License** | ![Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg) |
| **Version** | ![v0.36.0-rc](https://img.shields.io/badge/version-v0.36.0--rc-blue) |

---

## Roadmap

- [x] v0.1.0-v0.20.0: Engineering infrastructure + Formal verification + Sidecar + Drift detection + Chaos engineering + A2A + Identity + Orchestration + Desktop Agent → GA
- [x] Phase Ω (R101-R150): 50 rounds of autonomous recursive evolution full reinforcement → v0.21.0 Final
- [x] v0.30.0-GA: Human-agent collaboration layer + Memory layer + Skill marketplace + National crypto SM2/SM3/SM4-GCM + Technical whitepaper
- [x] v0.35.0-rc: Loop Engineering narrative layer + Three meta-pattern architecture design + Verifier cross-validation + 60%+ module coverage
- [x] v0.36.0-rc: `maref.loop` module implementation — ConvergentLoop / ExploratoryLoop / InteractiveLoop + LoopGovernanceBridge + TrustBoundary integration
- [ ] v1.0: Full recursive evolution stack + Agent credit rating + Four-phase governance model
- [ ] v2.0: Meta-agent closure + Carbon-silicon symbiosis + Eight-trigram governance

---

## License

Apache License 2.0 — [LICENSE](LICENSE)
