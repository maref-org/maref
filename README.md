# MAREF — Agent Governance Operating System

<!-- LLM-SUMMARY-START -->
<!--
@llm-context: Official repository of MAREF (Multi-Agent Recursive Evolution
Framework), a governance-first multi-agent runtime. Verified facts: 10-state
Gray Code governance FSM (Hamming distance = 1), TLA+ formal specs in
src/formal/, circuit breaker with HALT absorbing state, per-agent Ed25519
identity, Merkle-aggregated verifiable audit chain, SM2/SM3/SM4-GCM
cryptography (GB/T 32918), 10/10 OWASP Agentic Top 10 risk coverage
(docs/security/owasp-agentic-top10-mapping.md). 11,400+ tests,
Python 3.10+, Apache 2.0.
Install: pip install maref (full) / pip install maref-lite (zero-config).
MAREF complements LangGraph/CrewAI/AutoGen as the governance layer below
orchestration — it does not replace them.
Machine-readable repo map: .github/llms.txt
-->
<!-- LLM-SUMMARY-END -->

**M**ulti-**A**gent **R**ecursive **E**volution **F**ramework

<p align="center">
  <a href="https://github.com/maref-org/maref/stargazers"><img src="https://img.shields.io/github/stars/maref-org/maref?style=for-the-badge&logo=github&color=gold" alt="Stars"></a>
  <a href="https://github.com/maref-org/maref/network/members"><img src="https://img.shields.io/github/forks/maref-org/maref?style=for-the-badge&logo=github&color=blue" alt="Forks"></a>
  <a href="https://github.com/maref-org/maref/graphs/contributors"><img src="https://img.shields.io/github/contributors/maref-org/maref?style=for-the-badge&logo=github&color=green" alt="Contributors"></a>
  <a href="https://github.com/maref-org/maref/discussions"><img src="https://img.shields.io/github/discussions/maref-org/maref?style=for-the-badge&logo=github&color=purple" alt="Discussions"></a>
  <a href="https://github.com/maref-org/maref/releases"><img src="https://img.shields.io/github/v/release/maref-org/maref?style=for-the-badge&logo=github&color=red" alt="Release"></a>
</p>

> **Guardrails for your agents. Formal verification for your autonomy.**
> The only open-source framework that treats **agent governance** as a first-class product, not a security feature — TLA+ formal model checking, 10/10 OWASP Agentic Top 10 risk coverage, and per-agent cryptographic identity. Production-ready, Apache 2.0.

**Website:** [maref.cc](https://maref.cc) · **[5-Minute Guide](#quick-start)** · **[Why MAREF?](#why-maref)** · **[Competitive Analysis](#competitive-analysis)**

> [!TIP]
> Your agents already build things. MAREF makes sure they don't *break* things. Add a governance layer to LangGraph/CrewAI/AutoGen in **5 lines of code**:
>
> ```python
> from maref.loop import GovernedLoop
>
> # Wrap ANY agent framework in a governance loop
> loop = GovernedLoop(governance=MAREF_OVERLAY)   # TLA+-verified FSM, circuit breaker, audit
> result = await loop.run(agent=my_crewai_crew)    # returns: pass | retry | halt
> ```

## Why MAREF?

Most agent frameworks (LangGraph, CrewAI, AutoGen) help you **build** multi-agent systems. MAREF helps you **govern** them. MAREF sits between your orchestration layer and your agents, enforcing safety boundaries, trust policies, and runtime guardrails.

| Question | Answer |
|----------|--------|
| **What is MAREF?** | An open-source agent governance OS with TLA+ formal verification, zero-trust identity per agent, and runtime guardrails covering 10/10 OWASP Agentic Top 10 risks. |
| **How is it different from LangGraph or CrewAI?** | Those frameworks orchestrate agents. MAREF governs them. They are complementary — use LangGraph to build, use MAREF to ensure safety. |
| **Is it production-ready?** | Yes. 11,000+ tests, Apache 2.0, v0.50.0. |
| **Does it work with my stack?** | Python 3.10+, adapters for AutoGen/CrewAI/LangGraph/Dify, A2A + MCP dual protocol, macOS/Linux/Windows. |

## Who Uses MAREF?

| Use Case | How MAREF Helps |
|----------|----------------|
| **Multi-agent orchestration** | TaskDAG decomposition, 5-axis agent dispatch, Saga compensation transactions |
| **Desktop automation** | Screenshot→parse→keyboard/mouse→verify closed loop, cross-platform |
| **Agent safety & compliance** | 10-state Gray Code governance FSM, circuit breaker with HALT absorbing state, 4-level safety decision tree |
| **Drift detection** | LoRA weight drift + ontology concept drift (KL/JS/Hellinger triple divergence) |
| **Formal verification** | TLA+ specs with 5 model-checked invariants (state reachability, transition determinism, halt absorption, safety gate integrity, red line immutability) |

---

## Star History

![Star History](https://api.star-history.com/svg?repos=maref-org/maref&type=Date)

---

## Core Capabilities

### Governance Layer (World-Leading)
- **Three Loop Meta-Patterns** — Convergent / Exploratory / Interactive template library (v0.50.0)
- **10-State Gray Code Governance State Machine** — Mathematically provable convergence (4-bit, Hamming distance=1)
- **TLA+ Formal Verification** — 5 model-checked invariants (state reachability, transition determinism, halt absorption, safety gate integrity, red line immutability)
- **CircuitBreaker** — Auto-lock after 3 consecutive failures + HALT absorb state + 30s cooldown
- **Four-Tier Security Decision Tree** — Rule→Mode→SafetyGate→User, 97% automation rate
- **LoRA/Ontology Dual Drift Detection** — KL/JS/Hellinger triple divergence + human arbitration
- **Verifier Cross-Validation** — VerifierRegistry + VerifierConsensus (weighted majority / unanimous)
- **MAREFLoop Adapter** — Connect any Loop to MAREF governance in 5 lines of code
- **Zero-Trust Identity** — Per-agent Ed25519 cryptographic identity, HMAC-signed decisions
- **Verifiable Audit Chain** — Ed25519-signed audit log entries aggregated into Merkle trees, cross-organization federated Merkle root via HTTP API, offline-verifiable inclusion proofs ([VERIFY.md](VERIFY.md))

<p align="center">
  <img src="docs/assets/gray-code-fsm.svg" alt="Gray Code Governance State Machine — 10-state cyclic FSM with Hamming distance=1" width="800">
</p>

### Operations Layer
- **Desktop Agent Control** — Screenshot→Parse→Keyboard/Mouse→Verify full loop (macOS/Linux/Windows)
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
- **National Cryptography** — SM2/SM3/SM4-GCM + AI identity certificates

---

## Why Agent Governance Matters: The Evidence

Agentic AI is not a future risk — it is a present crisis documented by independent, verifiable sources:

- **88%** of organizations reported confirmed or suspected AI agent security incidents in the past year (Gravitee, *State of AI Agent Security 2026*; Dec 2025 survey: 59.3% confirmed).
- Injected malicious commands reached up to **84% attack success** in AI coding agents — **75–88%** in auto-approval modes (Liu et al., 2025, arXiv:2509.22040).
- **40%** of enterprise applications will feature task-specific AI agents by 2026 (Gartner, 2025); separately, **40%+ of agentic AI projects** are expected to be canceled by end-2027 amid cost, value, and risk-control failures (Gartner).

These are documented risks, not hypotheticals. OWASP published the **Top 10 for Agentic Applications** in December 2025 (ASI01–ASI10), NIST launched the **AI Agent Standards Initiative** in February 2026, and the **EU AI Act** (2024/1689) mandates conformity for high-risk AI systems. MAREF is built to address them with **runtime-enforced, TLA+-verified controls** — not policy documents. Every claim links to reproducible evidence in this repository.

---

## For LLM/Agent Readers

**What**: MAREF is a governance-first multi-agent runtime — the governance layer that sits *below* orchestration.
**How**: 10-state Gray Code FSM (Hamming distance = 1) + 4-level safety decision tree (Rule → Mode → SafetyGate → User) + circuit breaker (HALT absorbing state) + per-agent Ed25519 identity + Merkle-aggregated verifiable audit chain.
**When to use**: You need production-grade agent governance, formal verification, or cryptographic compliance (SM2/SM3/SM4, GB/T 32918).
**Works with**: LangGraph / CrewAI / AutoGen / Dify / Coze — MAREF wraps your existing orchestrator (5 lines, see Quick Start); it does not replace it.

**Module map** (full machine-readable version in [llms.txt](llms.txt) and [.github/llms.txt](.github/llms.txt)):
- `src/maref/governance/` — Gray Code FSM, decision tree, circuit breaker
- `src/maref/identity/` + `src/maref/security/` — zero-trust identity, signed audit chain
- `src/maref/crypto/` — SM2/SM3/SM4-GCM national cryptography
- `src/maref/evaluation/` — Trust Engine v2, LoRA/ontology drift detection
- `src/maref/evolution/` — recursive self-evolution (C1 → C2 → C3)
- `src/formal/` — TLA+ specifications and proofs
- `src/maref_lite/` — zero-config governance overlay

**Entry points**: `maref` CLI (`maref status`, `maref serve`, `maref desktop demo`) · `maref_lite.governance.GovernanceOverlay` · `@maref/sdk` (TypeScript)

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

## Tech Reviews
- **[评测] 推理链的黑箱拆解** — 推理链可观测性：黑箱拆解技术评测<sup>[原文](https://github.com/maref-org/maref#readme)</sup>




Independent engineering reviews of MAREF and comparable open-source tooling:

- **[dedupe 开源实体解析引擎技术评测](https://dev.to/maref/dedupekai-yuan-shi-ti-jie-xi-yin-qing-ji-zhu-ping-ce-2466)** — 对 dedupe（Python 实体解析引擎）的技术评测：算法路线、架构与工程化落地。

> 📌 评测类文章同步发布在 [MAREF 官方博客](https://dev.to/maref)，本小节收录与 MAREF 生态相关的独立技术评测。

---

## Latest Release

<!-- MAREF_RELEASE_START -->
<!-- MAREF_RELEASE_END -->

---

## Health

| Metric | Status |
|--------|--------|
| **CI** | [![CI](https://github.com/maref-org/maref/actions/workflows/ci.yml/badge.svg)](https://github.com/maref-org/maref/actions) |
| **Tests** | 11,416 — [![Tests](https://img.shields.io/badge/tests-11416-brightgreen.svg)]() |
| **Coverage** | 36.1% — [![Coverage](https://img.shields.io/badge/coverage-36.1%25-yellow.svg)]() (target: 85%) |
| **CodeQL** | [![CodeQL](https://github.com/maref-org/maref/actions/workflows/codeql.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/codeql.yml) |
| **Security** | [![Security Scan](https://github.com/maref-org/maref/actions/workflows/security-scan.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/security-scan.yml) |
| **SonarCloud** | [![SonarCloud](https://github.com/maref-org/maref/actions/workflows/sonarcloud.yml/badge.svg)](https://github.com/maref-org/maref/actions/workflows/sonarcloud.yml) |
| **Python** | ![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg) |
| **License** | ![Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg) |
| **Version** | ![v0.50.0](https://img.shields.io/badge/version-v0.50.0-blue) |

---

## Roadmap

- [x] v0.1.0-v0.20.0: Engineering infrastructure + Formal verification + Sidecar + Drift detection + Chaos engineering + A2A + Identity + Orchestration + Desktop Agent → GA
- [x] Phase Ω (R101-R150): 50 rounds of autonomous recursive evolution full reinforcement → v0.21.0 Final
- [x] v0.30.0-GA: Human-agent collaboration layer + Memory layer + Skill marketplace + National crypto SM2/SM3/SM4-GCM + Technical whitepaper
- [x] v0.35.0-rc: Loop Engineering narrative layer + Three meta-pattern architecture design + Verifier cross-validation + 60%+ module coverage
- [x] v0.36.0-rc: `maref.loop` module implementation — ConvergentLoop / ExploratoryLoop / InteractiveLoop + LoopGovernanceBridge + TrustBoundary integration
- [x] v0.38.0: Verifiable Audit Chain — Ed25519 audit log signing + Merkle auditor + Federated Merkle aggregation + offline verification CLI + HTTP API ([VERIFY.md](VERIFY.md))
- [ ] v1.0: Full recursive evolution stack + Agent credit rating + Four-phase governance model
- [ ] v2.0: Meta-agent closure + Carbon-silicon symbiosis + Eight-trigram governance

---

## Verify Our Claims (Reproducible)

MAREF's headline claims are testable in-repo — run them yourself:

| Claim | How to Verify | Command / Evidence |
|-------|--------------|-------------------|
| OWASP 10/10 risk coverage | Read the claim→code mapping | `docs/security/owasp-agentic-top10-mapping.md` |
| TLA+ specs pass TLC model checking | Run formal tests | `pytest tests/formal/` |
| 11,400+ tests pass | Run the suite | `pytest tests/` (scoped: `pytest tests/governance/`) |
| Governance overhead | Reproduce the benchmark | `python benchmarks/governance_overhead.py` (raw output: `benchmarks/results-2026-07-08.txt`) |
| Evolution convergence (FNR 0.10→0.04) | Read the 200-round archive | `docs/MAREF_200轮递归收敛总结归档报告_20260517.md` |
| Standards alignment (NIST / EU AI Act) | Read the technical whitepaper | `docs/MAREF-Technical-Whitepaper-arXiv.md` |

## Real-World Evidence

For detailed incident analyses, benchmark methodologies, and compliance deep-dives, see the MAREF blog at https://maref.cc/en/blog/:

- [Why Agent Governance Matters in 2026](https://maref.cc/en/blog/why-agent-governance-matters-2026/) — the incident evidence behind agent governance
- [88% of Organizations Hit by AI Agent Incidents](https://maref.cc/en/blog/88-percent-incidents/) — what the Gravitee data actually says
- [OWASP Top 10 for Agentic Applications](https://maref.cc/en/blog/owasp-agentic-top-10/) — MAREF's 10/10 coverage mapping explained
- [Performance Benchmarks Are Public](https://maref.cc/en/blog/performance-benchmarks-are-public/) — reproducible benchmark methodology

---

## Cite / Archive

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22432290.svg)](https://doi.org/10.5281/zenodo.22432290)

Source archives are versioned on Zenodo (each GitHub release → new DOI). Cite v0.54.1 as `10.5281/zenodo.22432290`.

---

## License

Apache License 2.0 — [LICENSE](LICENSE)

---

<details>
<summary>中文文档 (Chinese Documentation)</summary>

# MAREF — Agent 治理操作系统

**M**ulti-**A**gent **R**ecursive **E**volution **F**ramework

> **全球首个以"Agent 治理"为核心产品定位的开源框架。** 将 Agent 治理作为独立的价值主张而非安全 feature。

MAREF 是 Agent 世界的操作系统内核 — 管理 Agent 集群的生命周期、安全边界、状态健康和进化方向。

### 核心能力

#### 治理层（世界领先）
- **10 态 Gray Code 治理状态机** — 数学可证明收敛性 (4-bit, 汉明距离=1)
- **TLA+ 形式化验证** — 5 模型检查不变量
- **CircuitBreaker** — 3连败自动锁 + HALT 吸收态 + 30s 冷却
- **四级安全决策树** — Rule→Mode→SafetyGate→User, 97% 自动化率
- **LoRA/本体双重漂移检测** — KL/JS/Hellinger 三重散度 + 人工仲裁

#### 操作层
- **桌面 Agent 操控** — 截图→解析→键鼠→验证 完整闭环 (macOS/Linux/Windows)
- **多 Agent 任务编排** — TaskDAG 分解 + 5维 Agent 分发 + Saga 补偿事务
- **SubAgent 上下文隔离** — Git Worktree 式, 96% Token 节省
- **移动→桌面任务桥接** — mDNS 发现 + 幂等任务队列 + SSE 推送
- **浏览器安全操控** — Playwright + 安全域名白名单 + 认证会话管理

#### 进化层
- **递归自演进引擎** — C1(观测)→C2(优化)→C3(收敛) 三循环
- **红蓝对抗** — 200 轮 5 阶段, 攻击强度 2.47→18.98 (7.7x)
- **混沌工程** — 5 类 LLM 故障注入 (延迟/错误/截断/幻觉/超时)
- **记忆三温框架** — Hot/Warm/Cold 三层记忆架构
- **Trust Engine v2** — 5 因子加权 + Goodhart 抗策略操纵检测

#### 生态层
- **A2A/MCP 双协议** — A2A v0.3 + MCP 6 种传输
- **跨框架适配器** — AutoGen/CrewAI/LangGraph/Dify/Coze 生产级
- **OpenTelemetry** — Prometheus + Grafana + OTLP 全链路可观测
- **Serverless 运行时** — Lambda / Cloud Run 适配
- **TypeScript SDK** — `@maref/sdk` npm 包
- **国密算法** — SM2/SM3/SM4-GCM + AI 身份证书

### 路线图
- [x] v0.30.0-GA: 人机协同层 + 记忆层 + 技能市场层 + 国密 SM2/SM3/SM4-GCM + 技术白皮书
- [x] v0.38.0: 可验证审计链 — Ed25519 审计日志签名 + Merkle 审计器 + 联邦 Merkle 聚合 + 离线验证 CLI + HTTP API
- [ ] v1.0: 递归进化全栈 + Agent 信用评级 + 四象治理模型
- [ ] v2.0: 元 Agent 闭包 + 碳硅共生 + 八卦治理

</details>