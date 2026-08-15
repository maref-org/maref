# MAREF 治理愿景草案 — 指引说明

> **状态**: 指针/指引文档（非实现说明）
> **日期**: 2026-08-15
> **性质**: 说明文档，不进入本仓库的架构/实现索引

## 这是什么

本条目指向 MAREF 的**治理愿景与未来路线草案**（原《MAREF 全量架构与治理白皮书 v1.0-draft》）。该草案经 2026-08-15 交叉验证后，确认与现行代码库实现存在重大差距，已**降级为"治理愿景/未来路线参考"**单独存放于内部知识库。

- **草案位置**（内部知识库，不在本仓库）: 内部知识库「项目知识库/maref/架构/MAREF治理愿景与未来路线草案-20260815.md」（内部卷路径不对外公开）

## ⚠️ 重要声明

该草案描述的"五层治理栈"及核心概念——四方审计代理（USA/MSA/ESA/RA）、认知阴影、MPCG 多方因果图谱、多 LLM 仲裁庭、WORM 物理黑匣子、VCP/FCG/FEP——在**当前代码库中零落地**，属治理愿景。MAREF 现行架构为**易经六层架构 + 8 层纵深防御**（见 `architecture.md`、`MAREF-Technical-Whitepaper-zh-CN.md`）。

**该草案不得作为 MAREF 对外白皮书或现行架构说明引用。**

## 已落地 vs 愿景（摘要）

| 概念 | 状态 | 证据坐标 |
|------|------|----------|
| 熔断器（CLOSED→OPEN→HALF_OPEN） | ✅ 已落地 | `src/maref/governance/circuit_breaker.py` |
| Sidecar 治理旁车 | ✅ 已落地 | `src/sidecar/server.py`、`Dockerfile.sidecar` |
| eBPF 内核探针 | ✅ 已落地 | `sentinel/platform/linux/bpf_probe.py` |
| 工具调用预检（fail-closed） | ✅ 已落地 | `maref-governance/src/index.ts` |
| 沙盒预演（WASM/策略） | ✅ 部分 | `src/maref/eivl/wasm_sandbox.py` |
| 信任评分（四档） | ✅ 已落地 | `src/maref/security/trust_api.py` |
| 规则仲裁 + 加权验证共识 | ✅ 已落地 | `governance/judge.py`、`verifier_consensus.py` |
| 10 态 Gray Code FSM + TLA+ + 国密 | ✅ 已落地 | `src/maref/recursive/`、`src/maref/formal/` |
| 五层治理栈 | ❌ 愿景（现行为易经六层） | `architecture.md:13-38` |
| 四方审计代理 USA/MSA/ESA/RA | ❌ 愿景 | 全仓零命中 |
| 认知阴影 / MPCG / WORM / TEE 证明 | ❌ 愿景 | 全仓零命中 |
| 多 LLM 仲裁庭（MRC） | ⚠️ 仅骨架 | `governance/judge.py:69` |
| VCP / FCG / FEP | ❌ 愿景 | 全仓零命中 |

## 处置建议

该草案保留为治理愿景参考，待后续版本规划（如 v0.55+）评估是否将其中概念纳入正式路线图。如需更新，以本仓库实际实现为准。
