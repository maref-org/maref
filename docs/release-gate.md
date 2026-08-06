# MAREF Release Gate v1.0

> **地位**: MAREF 自有的轻量发布门禁。本仓库一切发布审计、Gate 决策、Go/No-Go 评估的唯一执行标准。
>
> **上位法**: Athena 系统宪法 v1.5（`docs/CONSTITUTION.md`）→ MAREF 开源执行规范 v1.0（`docs/oss-execution-norm-v1.0.md`）→ AGENTS.md → 本文件。
>
> **适用范围**: MAREF 仓库（Track B 发布源）。本仓库为纯后端 Agent 治理 OS，L3 前端层 / L4 UI 层 / 桌面端专项审计不适用（生态前端 openclaw / Athena-UI 另行规范）。
>
> **替代声明**: 本文件取代任何外部项目手册（包括但不限于 SkillOS `SKILLOS-RELEASE-HANDBOOK-001`、`ENG-RELEASE-HANDBOOK-001` 等）作为 MAREF 发布依据。外部手册仅可作参考资料。
>
> **生效日期**: 2026-06-19 · **维护方**: MAREF Engineering Excellence Team

---

## 1. 10 项轻量门禁

| # | 门禁 | 通过标准 | 自动化工具 / 命令 | 对应宪法条款 |
|---|------|---------|-------------------|-------------|
| **G1** | 宪法符合性 | 上位法引用链完整；无 `SKILLOS-` / `ENG-*-HANDBOOK` 等外部编号被引用为依据；`docs/CONSTITUTION.md` 在位 | `scripts/ci-governance-check.sh` 上位法白名单段 | 第一条 / 第十一条 |
| **G2** | 代码质量 | Ruff 0 violations；Mypy strict 0 errors；0 硬编码 `/Volumes/` 等本地路径；0 nested `.git` | `ruff check src/maref src/maref_lite` · `mypy src/` · `.github/workflows/release-gate.yml:gate-quality` | 第二条 |
| **G3** | 静态安全 (SAST) | 0 Critical / 0 High | Bandit + Semgrep + CodeQL + SonarCloud | 第二条 / 第五条 |
| **G4** | 依赖审计 (SCA) | 0 Critical CVE；许可证无 GPL/SSPL 污染 | `pip-audit` · `cargo audit`（gui/src-tauri）· Trivy · Dependabot | 第九条 |
| **G5** | 密钥扫描 | 0 硬编码密钥；`.gaas_api_key` 在 `.gitignore` | TruffleHog / GitLeaks · `.github/workflows/release-gate.yml:gate-security` | 第五条 / 第六条 |
| **G6** | 测试套件 | 全绿；覆盖率 ≥ 当前版本阈值（Experimental ≥ 30%、Beta ≥ 60%、GA ≥ 70%；核心模块 ≥ 90%） | `pytest tests/ -v --cov=src/maref --cov-fail-under=N` | 第七条 |
| **G7** | SAEB 递归基准 | `tests/benchmark/test_saeb.py` 14/14 全绿；免疫系统自 SAEB 0 退化 | `pytest tests/benchmark/test_saeb.py -v` | 第七条 / 第八条 |
| **G8** | 形式化验证 | TLA+ 模型检验通过（宪法红线 5 不变量 + GrayCodeTransition + LyapunovConvergence） | `cd src/formal && java -cp tla2tools.jar tlc2.TLC -config MAREF_ConstitutionalRedLinesMC.cfg MAREF_ConstitutionalRedLines` | 第三条 / 第八条 |
| **G9** | 治理钩子集成 | `scripts/hook-gaas-client.py` 在位；`src/sidecar/gaas_router.py` 在位（若 sidecar 目录存在）；`governance_router.py` 含 `git.push` / `git.commit` 策略；CLAUDE.md 含宪法关键词 ≥ 3/3 | `scripts/ci-governance-check.sh` | 第十条 |
| **G10** | 回滚就绪 | 数据库变更脚本有逆向脚本；上一版本 Docker 镜像保留；MAREF Lite CLI 可回到上一版本；功能开关默认值与回滚策略文档化 | 人工 + `packaging/verify-sidecar.sh` | 第二条 / 第四条 |

## 2. 成熟度分级（与 AGENTS.md 对齐）

| 等级 | 必过门禁 | 例外上限 | 决策 |
|------|---------|---------|------|
| **Experimental** | G1, G2, G3, G5, G6 (≥30%), G9 | G4/G7/G8/G10 允许降级说明 | 可降级运行 |
| **Beta** | G1~G9（G6 ≥ 60%） | 至多 2 个例外（须带到期时间） | 需审批 |
| **GA** | G1~G10 全过（G6 ≥ 70%） | 0 例外 | 全票 Go |

## 3. Gate 流程映射（轻量级）

```
Gate 0 需求冻结   →  宪法符合性预审 (G1)
Gate 1 开发完成   →  G2/G3/G5/G9 自动化
Gate 2 内测通过   →  G6/G7 测试与递归基准
Gate 3 预发验收   →  G4/G8 形式化与依赖审计 + G10 回滚演练
Gate 4 生产发布   →  Go/No-Go 决策会（全票或条件 Go）
```

## 4. Go / No-Go 决策

- **Go**: G1~G10（按目标成熟度对应集）全过，残余风险可接受。
- **Conditional Go**: 仅剩非阻塞项且每项有到期缓解措施；不得标记为 GA。
- **No-Go**: 任一阻塞门禁未过，或宪法红线被削弱，或出现外部上位法污染（如 `SKILLOS-` 引用回潮）。

## 5. 发布后监控

| 时间 | 动作 |
|------|------|
| T+1h | sidecar `/api/health` 与 GaaS 钩子自检通过 |
| T+24h | 对比发布前后 SAEB 基线与覆盖率 |
| T+7d | 收集 issue 与红蓝对抗结果 |
| T+30d | 发布质量评分纳入团队 KPI |

## 6. 与外部手册的关系

任何引用外部手册（SkillOS、ENG-LAUNCH-CHECKLIST 等）作为 MAREF 审计依据的行为，**自动触发 G1 失败**。外部手册内容如可借鉴，须经宪法符合性审查后**重新编入本文件**方可生效。

---

## Changelog

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-06-19 | 首版。10 项轻量门禁确立，取代 SkillOS `SKILLOS-RELEASE-HANDBOOK-001` 在本仓库的依据地位。 |
