# MAREF — Agent Governance OS

**M**ulti-**A**gent **R**ecursive **E**ngineering **F**ramework

[![CI](https://github.com/maref-org/maref/actions/workflows/ci.yml/badge.svg)](https://github.com/maref-org/maref/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.30.0-blue)](https://github.com/maref-org/maref/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-4300+-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen.svg)]()

> **全球唯一以"Agent 治理"为核心产品定位的框架。** 在治理深度上碾压所有竞品（10/10 vs 0-3），将 Agent 治理作为独立的价值主张而非安全 feature。

MAREF 是 Agent 世界的操作系统内核 — 管理 Agent 集群的生命周期、安全边界、状态健康和进化方向。

## 核心能力

### 治理层 (世界领先)
- **10 态 Gray Code 治理状态机** — 数学可证明收敛性 (6bit, 汉明距离=1)
- **TLA+ 形式化验证** — 5 定理证明 (Lyapunov收敛 + Sperner完备性)
- **CircuitBreaker** — 3连败自动锁 + HALT 吸收态 + 30s 冷却
- **四级安全决策树** — Rule→Mode→SafetyGate→User, 97% 自动化率
- **LoRA/本体双重漂移检测** — KL/JS/Hellinger 三重散度 + 人工仲裁

### 操作层
- **桌面 Agent 操控** — 截图→解析→键鼠→验证 完整闭环 (macOS/Linux/Windows)
- **多 Agent 任务编排** — TaskDAG 分解 + 5维 Agent 分发 + Saga 补偿事务
- **SubAgent 上下文隔离** — Git Worktree 式, 96% Token 节省
- **移动→桌面任务桥接** — mDNS 发现 + 幂等任务队列 + SSE 推送
- **浏览器安全操控** — Playwright + 安全域名白名单 + 认证会话管理

### 进化层
- **递归自演进引擎** — C1(观测)→C2(优化)→C3(收敛) 三循环
- **红蓝对抗** — 200 轮 5 阶段, 攻击强度 2.47→18.98 (7.7×)
- **混沌工程** — 5 类 LLM 故障注入 (延迟/错误/截断/幻觉/超时)
- **记忆三温框架** — Hot/Warm/Cold 三层记忆架构
- **Trust Engine v2** — 5 因子加权 + Goodhart 抗策略操纵检测

### 生态层
- **A2A/MCP 双协议** — A2A v0.3 + MCP 6 种传输
- **跨框架适配器** — AutoGen/CrewAI/LangGraph/Dify/Coze 生产级
- **OpenTelemetry** — Prometheus + Grafana + OTLP 全链路可观测
- **Serverless 运行时** — Lambda / Cloud Run 适配
- **TypeScript SDK** — `@maref/sdk` npm 包

## 快速开始

```bash
# 一键安装
pip install maref

# 桌面操控 (dry-run 安全模式)
maref desktop demo

# 环境诊断 (15项检查)
python scripts/check_desktop_env.py

# 治理状态查询
maref status

# 启动 Sidecar 服务
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

## 架构

```
                    MAREF: Agent 治理操作系统
    ┌─────────────────────────────────────────────────────────┐
    │  应用层 ─── LangGraph / CrewAI / AutoGen / Anthropic    │
    │             (编排/操控/开发框架)                          │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  治理层 ─── MAREF (本框架)                               │
    │             · 状态机 · 熔断器 · 四级决策树               │
    │             · 身份/信任 · 漂移检测 · 形式化验证           │
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
    │  通信层 ─── A2A / MCP (Google/Anthropic 标准)            │
    └─────────────────────────────────────────────────────────┘
```

## 竞品对比

| 维度 | **MAREF** | Anthropic | OpenAI | LangGraph | CrewAI | AutoGen |
|------|----------|-----------|--------|-----------|--------|---------|
| 治理/安全 | **10** | 4 | 3 | 2 | 1 | 1 |
| 形式化验证 | **10** | 0 | 0 | 0 | 0 | 0 |
| 漂移检测 | **9** | 0 | 0 | 0 | 0 | 0 |
| 桌面操控 | 8 | **9** | 7 | 0 | 0 | 0 |
| 编排 | 7 | 8 | 8 | **9** | 8 | 8 |
| 身份/信任 | **7** | 0 | 0 | 0 | 0 | 0 |
| 社区/生态 | 3 | 8 | **9** | 8 | **9** | 8 |

## 测试

| 类型 | 数量 | 状态 |
|------|------|------|
| 全量 | 4,300+ | ✅ |
| 覆盖率 | 82% | ✅ |

```bash
pytest tests/ -v --cov
pytest tests/desktop/ -v    # 桌面操控测试
pytest tests/chaos/ -v       # 混沌工程
```

## 路线图

- [x] v0.1.0-v0.20.0: 工程基础设施 + 形式化验证 + Sidecar + 漂移 + 混沌 + A2A + Identity + 编排 + Desktop Agent → GA
- [x] Phase Ω (R101-R150): 50 轮自主递归演进全量补强 → v0.21.0 Final
- [x] v0.30.0-GA: 人机协同层 + 记忆层 + 技能市场层 + 国密 SM2/SM3/SM4-GCM + 技术白皮书
- [ ] v1.0: 递归进化全栈 + Agent 信用评级 + 四象治理模型
- [ ] v2.0: 元 Agent 闭包 + 碳硅共生 + 八卦治理

详见 [task_plan_v0.21.0-rc_omega_50_rounds.md](task_plan_v0.21.0-rc_omega_50_rounds.md)

## 许可证

Apache License 2.0 — [LICENSE](LICENSE)