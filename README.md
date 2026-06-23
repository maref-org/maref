# MAREF — Agent Governance Operating System

**M**ulti-**A**gent **R**ecursive **E**volution **F**ramework

[![CI](https://github.com/maref-org/maref/actions/workflows/ci.yml/badge.svg)](https://github.com/maref-org/maref/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.30.0-blue)](https://github.com/maref-org/maref/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-4300+-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen.svg)]()

> The only open-source framework that treats **agent governance** as a first-class product, not a security feature. TLA+ formal verification, 10/10 OWASP Agentic Top 10 risk coverage, and per-agent cryptographic identity — production-ready, Apache 2.0.

**Website:** [maref.cc](https://maref.cc) | **Docs:** [Quickstart](https://maref.cc/en/docs/quickstart/) | **Blog:** [Agent Governance](https://maref.cc/en/blog/)

## Why MAREF?

Most agent frameworks (LangGraph, CrewAI, AutoGen) help you **build** multi-agent systems. MAREF helps you **govern** them. MAREF sits between your orchestration layer and your agents, enforcing safety boundaries, trust policies, and runtime guardrails.

| Question | Answer |
|----------|--------|
| **What is MAREF?** | An open-source agent governance OS with TLA+ formal verification, zero-trust identity per agent, and runtime guardrails covering 10/10 OWASP Agentic Top 10 risks. |
| **How is it different from LangGraph or CrewAI?** | Those frameworks orchestrate agents. MAREF governs them. They are complementary — use LangGraph to build, use MAREF to ensure safety. |
| **Is it production-ready?** | Yes. 4,300+ tests, 82% coverage, Apache 2.0, v0.30.0-GA. |
| **Does it work with my stack?** | Python 3.10+, adapters for AutoGen/CrewAI/LangGraph/Dify, A2A + MCP dual protocol, macOS/Linux/Windows. |

## Who Uses MAREF?

| Use Case | How MAREF Helps |
|----------|----------------|
| **Multi-agent orchestration** | TaskDAG decomposition, 5-axis agent dispatch, Saga compensation transactions |
| **Desktop automation** | Screenshot→parse→keyboard/mouse→verify closed loop, cross-platform |
| **Agent safety & compliance** | 10-state Gray Code governance FSM, circuit breaker with HALT absorbing state, 4-level safety decision tree |
| **Drift detection** | LoRA weight drift + ontology concept drift (KL/JS/Hellinger triple divergence) |
| **Formal verification** | TLA+ specs with 5 proven theorems (Lyapunov convergence + Sperner completeness) |

## Core Capabilities

### Governance Layer (World-Leading)
- **10-state Gray Code governance state machine** — mathematically provable convergence (6-bit, Hamming distance=1)
- **TLA+ formal verification** — 5 theorems proven (Lyapunov convergence + Sperner completeness)
- **CircuitBreaker** — 3-strike auto-lock + HALT absorbing state + 30s cooldown
- **4-level safety decision tree** — Rule→Mode→SafetyGate→User, 97% automation rate
- **LoRA/ontology dual drift detection** — KL/JS/Hellinger triple divergence + human arbitration
- **Zero-trust identity** — per-agent Ed25519 cryptographic identity, HMAC-signed decisions

### Operations Layer
- **Desktop agent control** — screenshot→parse→keyboard/mouse→verify closed loop (macOS/Linux/Windows)
- **Multi-agent task orchestration** — TaskDAG decomposition + 5-axis agent dispatch + Saga compensation
- **SubAgent context isolation** — Git Worktree-style, 96% token savings
- **Mobile→desktop task bridge** — mDNS discovery + idempotent task queue + SSE push
- **Browser automation** — Playwright + secure domain allowlist + auth session management

### Evolution Layer
- **Recursive self-evolution engine** — C1(observe)→C2(optimize)→C3(converge) triple loop
- **Red-blue adversarial testing** — 200 rounds, 5 phases, attack intensity 2.47→18.98 (7.7x)
- **Chaos engineering** — 5 LLM failure injection types (latency/error/truncation/hallucination/timeout)
- **Three-temperature memory** — Hot/Warm/Cold tiered memory architecture
- **Trust Engine v2** — 5-factor weighted + Goodhart anti-gaming detection

### Ecosystem Layer
- **A2A/MCP dual protocol** — A2A v0.3 + MCP 6 transport types
- **Cross-framework adapters** — AutoGen/CrewAI/LangGraph/Dify/Coze production-ready
- **OpenTelemetry** — Prometheus + Grafana + OTLP full-chain observability
- **Serverless runtime** — Lambda / Cloud Run compatible
- **TypeScript SDK** — `@maref/sdk` npm package
- **Cryptography** — SM2/SM3/SM4-GCM (Chinese national standards) + AI identity certificates

## Quick Start

```bash
# Install
pip install maref

# Desktop demo (dry-run safe mode)
maref desktop demo

# Governance status check
maref status

# Start Sidecar service
maref serve --port 8000 --gui
```

```python
from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceState

overlay = GovernanceOverlay()
overlay._state_machine.transition(GovernanceState.OBSERVE)
overlay._state_machine.transition(GovernanceState.ANALYZE)
print(overlay.get_status())
```

## Architecture

```
                    MAREF: Agent Governance OS
    +-----------------------------------------------------------+
    |  Application  --- LangGraph / CrewAI / AutoGen / Anthropic |
    |                 (orchestration / automation frameworks)     |
    |  - - - - - - - - - - - - - - - - - - - - - - - - - - - -  |
    |  Governance  --- MAREF (this framework)                    |
    |                 . State Machine . Circuit Breaker          |
    |                 . Identity/Trust . Drift Detection         |
    |                 . Formal Verification . Safety Gates       |
    |  - - - - - - - - - - - - - - - - - - - - - - - - - - - -  |
    |  Transport   --- A2A / MCP (Google/Anthropic standards)   |
    +-----------------------------------------------------------+
```

## Competitive Comparison

| Dimension | **MAREF** | Anthropic | OpenAI | LangGraph | CrewAI | AutoGen |
|-----------|----------|-----------|--------|-----------|--------|---------|
| Governance/Safety | **10** | 4 | 3 | 2 | 1 | 1 |
| Formal Verification | **10** | 0 | 0 | 0 | 0 | 0 |
| Drift Detection | **9** | 0 | 0 | 0 | 0 | 0 |
| Desktop Control | 8 | **9** | 7 | 0 | 0 | 0 |
| Orchestration | 7 | 8 | 8 | **9** | 8 | 8 |
| Identity/Trust | **7** | 0 | 0 | 0 | 0 | 0 |
| Community | 3 | 8 | **9** | 8 | **9** | 8 |

## Testing

| Type | Count | Status |
|------|-------|--------|
| Total tests | 4,300+ | Passing |
| Coverage | 82% | Passing |

```bash
pytest tests/ -v --cov
pytest tests/desktop/ -v    # Desktop control tests
pytest tests/chaos/ -v      # Chaos engineering
```

## Roadmap

- [x] v0.1.0-v0.20.0: Engineering infrastructure + formal verification + sidecar + drift + chaos + A2A + identity + orchestration + desktop agent → GA
- [x] Phase Omega (R101-R150): 50 rounds autonomous recursive evolution → v0.21.0 Final
- [x] v0.30.0-GA: Human-agent collaboration + memory layer + skill marketplace + SM2/SM3/SM4-GCM cryptography + technical whitepaper
- [ ] v1.0: Full-stack recursive evolution + agent credit rating + four-quadrant governance model
- [ ] v2.0: Meta-agent closure + carbon-silicon symbiosis + eight-trigrams governance

## License

Apache License 2.0 — [LICENSE](LICENSE)

---

<details>
<summary>中文文档 (Chinese Documentation)</summary>

# MAREF — Agent 治理操作系统

**M**ulti-**A**gent **R**ecursive **E**volution **F**ramework

> **全球唯一以"Agent 治理"为核心产品定位的框架。** 在治理深度上碾压所有竞品（10/10 vs 0-3），将 Agent 治理作为独立的价值主张而非安全 feature。

MAREF 是 Agent 世界的操作系统内核 — 管理 Agent 集群的生命周期、安全边界、状态健康和进化方向。

### 核心能力

#### 治理层（世界领先）
- **10 态 Gray Code 治理状态机** — 数学可证明收敛性 (6bit, 汉明距离=1)
- **TLA+ 形式化验证** — 5 定理证明 (Lyapunov收敛 + Sperner完备性)
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
- [ ] v1.0: 递归进化全栈 + Agent 信用评级 + 四象治理模型
- [ ] v2.0: 元 Agent 闭包 + 碳硅共生 + 八卦治理

</details>
