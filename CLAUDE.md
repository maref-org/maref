# MAREF — Agent 自治理规范

> **上位法**: 本文件受 [Athena 系统宪法 v1.5](/Volumes/1TB-M2/public/CONSTITUTION.md) 和 [MAREF 治理框架](GOVERNANCE.md) 共同约束。冲突时以宪法优先，其次以治理框架为准。
> **项目状态**: 见 `STATE.yaml`
> **同步方向**: A → B 单向（Athena 开发源 → GitHub 发布源）

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

## 治理优先声明

本配置文件与 MAREF 治理框架冲突时，以治理框架为准。

## 安全红线（Article 4-A，完整 6 条）

1. `git remote -v` 必须仅显示授权 remote
2. 禁止绕过 pre-push hook（`--no-verify`）
3. 禁止将 Athena 专有文件（SOUL.md / IDENTITY.md / .openclaw/ 等）提交到此仓库
4. 禁止 `gh` CLI 推送到非授权远程
5. CD pipeline（cd.yml）必须处于禁用状态
6. Agent 启动时必须验证 remote 为授权 remote

## 工作区切换规则（Article 30）

当 Agent 在 openclaw 和外部工作区之间切换时：
- **openclaw 目录** → 执行完整预检（remote 验证 + pre-push hook 检查）
- **外部工作区目录** → 不适用 openclaw remote 检查，但须遵守：
  - 第三十二条（Track B 宪法约束）：本仓库 AGENTS.md 含宪法引用
  - 第九条（叙事转化）：发布前须处理 T3/T2 内容
- **子 Agent 宪法传递**：通过 Task tool 派生子 Agent 时，任务指令中必须包含第三十条预检要求和第四-A条安全红线摘要

## 文档来源层级（Article 31-A 皮质层）

```
L0（权威源）:  Athena知识库/003-open human（碳硅基共生）/018-v0.2.0-活跃/021-架构设计/MAREF递归演进框架/
L1（代码配套）: public/maref/docs/
L2（公开参考）: GitHub 对应仓库
```

执行规则:
1. 优先选择层级最高的来源（L0 > L1 > L2）
2. L0 找不到时降级到 L1
3. L2 仅用于对外回复时的公开信息确认
