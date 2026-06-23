# OSS 执行规范 v1.0 — MAREF Track B

> **上位法**: 本文件受 [MAREF 宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md) 约束。
> **范围**: MAREF 开源仓库 Track B（发布源），适用于所有 Code Agent 操作。
> **同步方向**: A → B 单向。Athena KB 是策略层，本仓库是执行层。

---

## 1. Agent 执行规则

### 1.1 启动预检

每次 Agent 会话启动时必须执行：

```bash
# 1. 确认 remote 状态
git remote -v  # 确认指向 github.com/maref-org/maref

# 2. 确认宪法红线
ls -la AGENTS.md  # 存在且可读

# 3. 确认当前版本
python3 -c "import sys; sys.path.insert(0, 'src'); from maref import __version__; print(__version__)"

# 4. 确认门禁状态
ruff check src/
mypy src/
```

### 1.2 禁止行为

| 规则 | 说明 |
|------|------|
| R1 | 禁止修改 `.missions/` 下的 validation-contract.md（仅 Orchestrator） |
| R2 | 禁止跨特征深度导入（每个特征目录独立） |
| R3 | 禁止绕过 TrustBoundaryManager 进行跨域调用 |
| R4 | 禁止硬编码密钥/凭证（必须用 keyring_store.py 或环境变量） |
| R5 | 禁止推送到 openclaw remote（闭源仓库） |

### 1.3 阶段切换条件

| 阶段 | 入口条件 | 出口条件 |
|------|---------|---------|
| Feature Development | PRD 已签审 | Code Review 通过 + 门禁 |
| Phase 0 (Tech Debt) | 无 | ruff 0 / mypy 0 / 覆盖率 ≥ 60% |
| Phase 1 (Iteration) | Phase 0 全部关闭 | 特征完成 + SAEB 无退化 |
| Release | 所有门禁通过 | GA 发布 |

---

## 2. 质量控制

### 2.1 交付物审查

| 类别 | 要求 | 自动检查 |
|------|------|---------|
| Python 代码 | ruff 0 / mypy 0 / pytest 通过 | CI |
| 测试覆盖率 | 核心模块 ≥ 80%, 整体 ≥ 60% | CI |
| 安全 | 0 Critical/High CVE / 0 密钥泄露 | TruffleHog / Trivy |
| 文档 | CHANGELOG 更新 / AGENTS.md 同步 | 人工 |

### 2.2 宪法自检

每次提交前执行：

```python
# 宪法红线验证
from maref.security.decorators import security_critical
from maref.recursive.meta_agent_closure import ConstitutionalRedLine

# 检查是否违反五条红线
assert not hasattr(ConstitutionalRedLine, "modified"), "RL-001: 不得修改安全红线"
```

---

## 3. 变更与修订

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-06-19 | 初始版本，适配 Track B 发布源 |

---

## 4. 外部 Agent 检查清单

当外部 Code Agent (OpenCode / Claude Code / Trae) 首次操作本仓库时：

- [ ] 已阅读 AGENTS.md（宪法红线）
- [ ] 已阅读 docs/oss-execution-norm-v1.0.md（本文件）
- [ ] 已确认 remote 状态（无 openclaw 泄露风险）
- [ ] 已运行启动预检（1.1 节）
- [ ] 已知悉禁止行为（1.2 节）
