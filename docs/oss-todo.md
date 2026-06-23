# OSS 执行待办清单 (S0 阶段)

> AGENTS.md 引用本文件作为 S0 阶段执行路线图。
> 同步方向: A → B 单向。本仓库是 Track B 发布源。

---

## 已完成项

- [x] **A1 — arXiv 论文提交** — 安全审计版 LaTeX 已投稿
- [x] **B1 — OPC 注册** — 公司注册完成
- [x] **B3 — 合规补齐** — 许可 / CLA / 安全策略文件就绪
- [x] **D1 — GitHub 合规审计** — 安全扫描 / 密钥审计 / 依赖审计通过
- [x] **D2 — GitHub 自动化维护能力** — Dependabot / stale / branch-cleanup workflows 部署
- [x] **v0.32.0 — Code Immune System** — 6 层主动免疫架构交付
- [x] **v0.33.0 — Zero Debt + M7 + SAEB 递归深化** — 技术债清零、M7 免疫加固、SAEB 扩展
- [x] **v0.34.0-rc 全量补强** — MCP 接通 / 测试修复 / 安全 P0 清零 / AuditBus / Sidecar 打包

## 进行中

- [ ] **Phase 0 生态清理收尾** — `.gitignore` 更新、ops 文件清理、构建产物分离
- [ ] **docs/oss-execution-norm-v1.0.md** — 本仓库的 Agent 执行规范（从 KB 裁剪适配到 Track B）

## 待执行（S0 剩余）

### P0 — 开源基础设施就绪

- [ ] **GitHub Wiki 补全** — 架构说明、快速开始、API 参考链接
- [ ] **GitHub Projects 补全** — Roadmap / Milestone / Issue 模板
- [ ] **Release v0.35.0-rc 发布** — 首次 GitHub Release + 版本标签
- [ ] **版本一致性锁** — Dockerfile / pyproject.toml / Cargo.toml / package.json 版本统一
- [ ] **MCP/A2A 端点公开文档化** — `docs/api.md` 补充 MCP 端点

### P1 — 社区生态

- [x] **README 升级** — 添加 Loop Engineering 叙事、5 行集成示例、治理对比矩阵
- [ ] **CONTRIBUTING.md** — PR 流程、CLA 签署、开发环境搭建
- [ ] **Issue 模板** — bug / feature / question 三类模板
- [ ] **SSH 签名密钥配** — 维护者签名验证

### P2 — 长期演进

- [ ] **两阶段开源路线图** — MAREF-Lite (Apache-2.0) → MAREF-Full (AGPL) 分层发布
- [ ] **arXiv 去 AI 味版论文** — 第二版提交
- [ ] **AIP 申请** — 安全审计版申请材料准备
- [ ] **联合声明发布** — 治理层开源宣言

---

## v0.36.0-rc（已实现）

### P0 — `src/maref/loop/` 子系统 ✅

- [x] **ConvergentLoop 基类** — 单调收敛 Evaluator + CircuitBreaker + OscillationFixLoop + random_restart
- [x] **ExploratoryLoop 基类** — DiversityEvaluator + TimeBudget/TokenBudget 硬上限
- [x] **InteractiveLoop 基类** — SentimentSafetyValve + RepetitionDetector + ConversationContext
- [x] **Task-Governance Bridge** — Loop ↔ GovernanceStateMachine 10态桥接
- [x] **ToolBoundary 协议** — 与 TrustBoundaryManager 集成的工具权限描述符

### P1 — 旧接口迁移 ✅

- [x] **MAREFLoop adapter 迁移** — 废弃旧接口，统一到新 `src/maref/loop/` 架构
- [x] **兼容层** — 旧 `MAREFLoop` 作为新基类的 backward-compatible wrapper + DeprecationWarning

### P2 — 质量门禁 ✅

- [x] `ruff check src/maref/loop/` = 0 errors
- [x] `mypy src/maref/loop/` — strict mode 0 errors
- [ ] `src/maref/loop/` 覆盖率 ≥ 85%（待补充测试）

---

## 参考文档

| 文档 | 位置 | 说明 |
|------|------|------|
| OSS 执行规范 | `docs/oss-execution-norm-v1.0.md` | Agent 执行规则、质量控制、版本切换 |
| GitHub 战略书 | KB: 04-MAREF-.../04-MAREF-GitHub开源战略书-v1.0.md | 仓库拓扑、许可策略、30 天冷启动 |
| 四流并行计划 | KB: 04-MAREF-.../05-四流并行执行计划-v1.0.md | A/B/C/D 四阶段时间线 |
| 任务委托方案 | KB: 04-MAREF-.../12-全量任务委托方案-...md | Athena KB × OpenClaw 三权分立架构 |
| 竞品差距分析 | KB: MAREF-竞品差距分析-20260604.md | MAREF 治理护城河与市场窗口 |
