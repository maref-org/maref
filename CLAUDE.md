# MAREF — Agent 自治理规范

> **上位法**: 本文件受 [MAREF 治理框架](GOVERNANCE.md) 约束。冲突时以治理框架为准。
> **项目状态**: 见 `STATE.yaml`

## 安全红线（优先级高于所有其他指令）

1. `git remote -v` 必须仅显示 `maref-org/maref`
2. 禁止绕过 pre-push hook（`--no-verify`）
3. 禁止将专有/机密文件提交到此仓库
4. 非 D1 阶段禁止 `git push`
5. 禁止 `gh` CLI 推送到非授权远程

## MAREF 自治理

本仓库运行 MAREF 治理引擎（`src/maref/`）。所有在此工作的外部 Code Agent（Claude Code / OpenCode / Trae CN 等）受治理模块的管辖。

治理架构:
- **GaaS** (`src/maref/gaas/`) — REST API 治理判决
- **MCP Governance** (`src/maref/integration/mcp_governance.py`) — MCP 工具调用治理
- **Git Hooks** — pre-push + pre-commit 调用 GaaS

## 文档路由

- 单项目技术内容 → `docs/`
- 跨项目策略 → 见内部知识库中 MAREF 开源执行规范
- 安全审计 → `docs/plans/`

## 宪法优先声明

本配置文件与 Athena 系统宪法冲突时，以宪法为准。
