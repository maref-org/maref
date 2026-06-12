# MAREF D1 Gate → Beta 补全工程实施计划

> **目标**: 基于审计结果（D级/49分），按 D1 Gate 优先路径推进至 Beta 级发布标准
> **依据**: `产品级发布全量验收标准与评审流程手册.md` §4, `STATE.yaml`, `docs/plans/2026-06-04-post-audit-reinforcement.md`
> **继承**: 本计划为 post-audit-reinforcement 的 Phase 6-8 增量补充，未完成的历史 Task 已重新映射

## D1 Gate 清单对照

| 检查项 | 当前 | 目标 | 映射 Sprint |
|--------|------|------|------------|
| G1 arXiv ID | ❌ | 有 arXiv 预印本 ID | Sprint 3 |
| G2 分支保护 | ✅ | 已启用 | — |
| G3 CI 绿色 | ❌ `fixing` | `pytest ✅ + ruff ✅ + mypy ✅` | **Sprint 1** |
| G4 安全干净 | ❌ `13 blocked` | 0 Critical/High | **Sprint 2** |
| G5 无运行时产物 | ❌ | 无 .db/.log/coverage | **Sprint 2** |
| **D1 Gate** | ❌ | ✅ | 3 个 Sprint |

## Sprint 架构

```
Sprint 1 (Phase 6): G3 打通 CI      → 3-4天
Sprint 2 (Phase 7): G4/G5 安全清理   → 3-4天
Sprint 3 (Phase 8): Beta 级全量审计  → 4-5天
                                    ─────────
                                    总计 ~2 周
```

---

## Sprint 1 — G3 打通 CI 绿色通道 (Phase 6)

**目标**: `pytest tests/ -v --cov` 通过 + ruff 0 error + mypy 0 real error

### Task 6-1: 修复测试基础设施（25 收集错误的根因）

**根因诊断**:
- `pyproject.toml` 仅定义了 `maref` 一个包
- `src/sidecar/`, `src/maref_lite/` 在目录中存在但未注册为可导入包
- 部分测试引用的模块（如 `sidecar.collector`）在此公开仓库中**不存在**（属于 上游开发仓库私有代码）
- 需要识别哪些测试是对应此仓库的实际模块，哪些是对应已裁剪模块的遗留测试

**Steps**:

1. 列举所有 MODULE_NOT_FOUND 错误并分类：
   - **A 类**：模块存在但路径不通 → 修复包发现
   - **B 类**：模块在此仓库不存在 → 删除测试或加 `pytest.mark.skip`

2. 修复 `pyproject.toml` 包发现（如果需要多包结构）：
   ```toml
   [tool.hatch.build.targets.wheel]
   packages = ["src/maref", "src/sidecar", "src/maref_lite", "src/drift_guard"]
   ```
   或改用 `find:` 策略。

3. 安装验证：
   ```bash
   pip install -e ".[dev,sidecar]" --no-build-isolation
   python -c "from sidecar.server import create_app; print('sidecar OK')"
   ```

4. 对 B 类缺失模块测试加 `@pytest.mark.skip(reason="module not in public repo")`。

**验证**: `pytest tests/ -v --cov=src/maref --cov-report=term-missing` 无收集错误

---

### Task 6-2: 修复 mypy 5 个实错（crypto/benchmark.py）

**继承**: post-audit-reinforcement Task 0-4 未完成部分

**文件**: `src/maref/crypto/benchmark.py`

**错误列表**:
```
benchmark.py:81: SM2KeyPair.generate → attr-defined
benchmark.py:105: tuple.ciphertext / tuple.tag → attr-defined
benchmark.py:121: SM2KeyPair.generate → attr-defined
benchmark.py:145: SM2KeyPair.generate → attr-defined
```

**根因**: `SM2KeyPair` 类型标注不匹配实际运行时类型。类方法 `generate` 返回类型与 mypy 推断不一致。

**修复方案**:
- 选项 A（推荐）：为 `SM2KeyPair` 添加准确类型标注，使用 `Protocol` 或 `TypeAlias`
- 选项 B：在 `benchmark.py` 加 `# type: ignore[attr-defined]`
- 选项 C：如果 `SM2KeyPair` 是 stub，修正 stub 签名

**验证**: `mypy src/` → 0 errors

---

### Task 6-3: 修复 ruff 24 个 E402 违规

**继承**: post-audit-reinforcement Phase 0 遗留

**文件**: `src/research/autoresearch_phase9.py`

**根因**: 条件导入和动态导入在模块顶部之后出现。

**修复方案**:
- 选项 A（推荐）：将导入移到文件顶部，或包裹在 `TYPE_CHECKING` 块中
- 选项 B：在该文件的 E402 上全局 `# noqa: E402`
- 选项 C（快速）：`ruff check --fix --unsafe-fixes src/research/autoresearch_phase9.py`

**验证**: `ruff check src/` → 0 errors

---

### Task 6-4: 清理脏工作树 — 提交已就绪的变更

**当前状态**: 9 个已修改 + 43+ 未跟踪文件

**方案**:
1. 检查哪些修改属已就绪修复（mypy、ruff、crypto 修复）
2. 分批提交，每批独立 message
3. 未跟踪的文件分类：
   - 测试文件 → 确认后提交
   - 脚本工具 → 提交
   - CI 配置 → 提交
   - 临时/产物文件 → 加入 `.gitignore` 或删除

**验证**: `git status` → 只有预期未跟踪文件（如 `.venv/`）

---

### Sprint 1 完成标准

```bash
# 三线全绿
pytest tests/ -v --cov=src/maref --cov-report=term-missing   # 无收集错误
ruff check src/                                                # 0 errors
mypy src/                                                      # 0 real errors
git status                                                     # 干净或仅预期文件
```

---

## Sprint 2 — G4/G5 安全清理 (Phase 7)

**目标**: 安全扫描 0 阻塞 + 无运行时产物 + 合规文档补齐

### Task 7-1: 审计 13 个安全发现并修复

**继承**: post-audit-reinforcement Phase 0 的遗留安全项

**Steps**:

1. 运行安全扫描工具识别具体发现：
   ```bash
   # 密钥扫描
   trufflehog filesystem . --config .trufflehog.yaml --since 2026-01-01
   # 容器扫描
   trivy image maref:latest
   # SCA 扫描
   snyk test --severity-threshold=high
   ```

2. 根据锁定的 13 个发现逐个修复：
   - 硬编码密钥 → 移入环境变量或 keyring_store.py
   - 依赖漏洞 → 升级版本
   - 容器漏洞 → 更新 base image
   - 配置泄露 → 移入 secrets

3. 每个修复独立 commit。

**验证**: `STATE.yaml` → `security_scan: clean (0 findings)`

---

### Task 7-2: 清理运行时产物

**G5 要求**: 仓库中不应存在 .db / .log / coverage 文件

**Steps**:

1. 检查当前产物：
   ```bash
   find . -name "*.db" -o -name "*.log" -o -name "coverage.*" -o -name "governance_observations*" | grep -v .venv | grep -v node_modules
   ```

2. 已处理：commit `6219a50` 停止跟踪 coverage.json 和 governance_observations.db。验证 `.gitignore` 覆盖。

3. 补充 `.gitignore` 规则：
   ```
   *.db
   *.log
   coverage/
   coverage.*
   .coverage*
   *.pyc
   __pycache__/
   ```

**验证**: `git status` 无运行时产物显示

---

### Task 7-3: 补齐缺失合规文档

**STATE.yaml 缺失项**: EAR export control, cryptography law audit, SBOM

**Steps**:

1. 创建 `docs/compliance/EAR_export_control.md`（声明 Apache-2.0 开源项目不受 EAR 管制）
2. 创建 `docs/compliance/cryptography_law_audit.md`（列举密码学使用 + 中国密码法合规说明）
3. 生成 SBOM：
   ```bash
   syft . -o spdx-json > sbom.spdx.json
   ```
4. 更新 `STATE.yaml`：
   ```yaml
   compliance_docs:
     EAR_export_control: present
     cryptography_law_audit: present
     SBOM: present
   ```

**验证**: `ls docs/compliance/` 含 2 文件，根目录含 `sbom.spdx.json`

---

### Task 7-4: 遗留 Phase 0 安全热修复收尾

**继承**: post-audit-reinforcement Phase 0 未完成项（从文档状态变为实际代码）

| 原 Task | 内容 | 优先级 |
|---------|------|--------|
| 0-1 | TruffleHog 配置 `.trufflehog.yaml` | P1 |
| 0-2 | API 密钥哈希（tenant.py） | **P0** |
| 0-5 | Electron sandbox 启用 | P1 |
| 0-7 | NetworkPolicy pod selector 修正 | P1 |
| 0-8 | HPA deployment 引用修正 | P1 |
| 0-9 | @security_critical 装饰器批量添加 | P1 |

每个 Task 3-5 步，沿用原计划的 Step 定义。

**验证**: `pytest tests/security/ -v` → 0 failures

---

### Sprint 2 完成标准

```bash
# G4 安全干净
trufflehog filesystem . --since 2026-01-01 | grep "Found" | wc -l   # 0
# G5 无产物
find . -name "*.db" -o -name "*.log" | grep -v .venv | wc -l        # 0
# STATE.yaml
grep "security_scan:" STATE.yaml      # clean
grep "EAR_export_control:" STATE.yaml # present
```

---

## Sprint 3 — Beta 级全量审计 (Phase 8)

**目标**: 达到手册 Beta 标准（全量审计，允许 2 个例外，Trace 贯通，错误码覆盖 80%）

### Task 8-1: arXiv 提交（G1 门禁）

**Steps**:
1. 完善 `docs/MAREF-Technical-Whitepaper-arXiv.md`（已存在）
2. 使用 `docs/arxiv-submission/` 中的模板格式化
3. 利用已获得的 1 个 endorsement 回复（STATE: `endorsement_replied: 1`）
4. 提交 arXiv

**验证**: `STATE.yaml` → `G1_arxiv_id: true`

---

### Task 8-2: 错误码覆盖 80% + 代码映射

**继承**: post-audit-reinforcement Task 2-2

**要求**: 后端错误码 → 前端用户提示文案 1:1 映射文档化，覆盖率 ≥ 80%

**Steps**:
1. 收集所有后端错误码（搜索 `raise HTTPException` / `return JSONResponse` 中的错误码）
2. 创建错误码矩阵文档 `docs/error-codes.md`
3. 确保前端 `ErrorDisplay` 组件消费 error.code
4. 添加 CI 检查：`python scripts/check_error_code_coverage.py` → ≥ 80%

**验证**: `python scripts/check_error_code_coverage.py` → Coverage ≥ 80%

---

### Task 8-3: Trace 贯通验证

**继承**: post-audit-reinforcement Task 2-3

**要求**: 前端生成 trace_id，贯穿后端所有调用，日志可串联查询

**Steps**:
1. 确认 `otel.ts` 中的 `injectTraceHeaders()` 已在 `client.ts` 中被调用
2. 确认后端 `otel_bridge.py` / `trace_context.py` 正确提取 trace 头
3. 端到端验证：启动 dev 环境 → 发起请求 → 检查日志串联
4. 文档化 Trace 贯通方案

**验证**: 手动端到端 trace 验证，或自动化 `tests/integration/test_trace_propagation.py`

---

### Task 8-4: 拜占庭共识验证 + 级联策略测试

**Beta 特有要求**:
- Byzantine Fault Tolerance 共识验证
- Cascade policy testing（级联策略测试）

**Steps**:
1. 运行现有 BFT 测试：`pytest tests/stress/test_consensus_byzantine_stress.py -v`
2. 如果测试不存在，创建最小 BFT 验证场景（3 节点，1 拜占庭）
3. 为级联策略编写测试（策略链：A→B→C，B 失败时级联影响验证）
4. 结果文档化

**验证**: `pytest tests/stress/test_consensus_byzantine_stress.py -v` → 0 failures

---

### Task 8-5: 遗留 Phase 1-5 高优任务收尾

从 post-audit-reinforcement 的 31 个 Task 中筛选 Beta 必须项：

| 原 Phase | Task | 内容 | Beta 必须 |
|----------|------|------|-----------|
| 1 | 1-1 | 版本标签统一 | ✅ |
| 1 | 1-2 | Snyk CI | ✅ |
| 1 | 1-3 | CodeQL | ✅ |
| 2 | 2-1 | OpenAPI 类型生成 | ✅ |
| 2 | 2-4 | 安全头中间件 | ✅ |
| 2 | 2-7 | /metrics 端点 | ⚠️ 可选 |
| 3 | 3-3 | Vitest CI | ⚠️ 可选 |
| 5 | 5-1 | Runbook | ✅ |
| 5 | 5-4 | 回滚脚本 CI | ✅ |

每个 Task 沿用原计划的 Step 定义，完成后勾选。

**验证**: 每个 Task 独立 commit + 验证

---

### Sprint 3 完成标准

```yaml
# STATE.yaml
d1_gate:
  G1_arxiv_id: true
  G3_ci_green: true
  G4_security_clean: true
  G5_no_runtime_artifacts: true
  gate_passed: true

# Beta 等级
错误码覆盖率: >= 80%
Trace贯通: 已验证 ✅
拜占庭共识: 测试通过 ✅
级联策略: 测试通过 ✅
```

---

## 执行方式

### 顺序规则
- Sprint 1 → Sprint 2 → Sprint 3 严格串行
- 每个 Sprint 内 Task 按编号顺序
- 前一个 Sprint 未完成时不得开始下一个

### 提交规范
```
fix(test): description           # Sprint 1
fix(security): description       # Sprint 2
feat(ops): description           # Sprint 3
```

### 验证门禁
每个 Task 完成后立即运行该 Task 的验证命令。
每个 Sprint 完成后运行 Sprint 完成标准的全部验证。
全部 3 个 Sprint 完成后运行全量验证：
```bash
pytest tests/ -v --cov=src/maref --cov-report=term-missing
ruff check src/
mypy src/
bash scripts/d1_preflight_check.py  # 若存在
```

### 回滚策略
每 2 个 Task 后做一次 `git commit`。如果某个 Task 引入故障，`git revert` 单个 commit。

---

## 附录：历史计划 Task 映射表

| 历史 Task | 当前归宿 | 说明 |
|-----------|---------|------|
| Phase 0 (全部 9 Task) | Sprint 2 Task 7-4 | 安全收尾 |
| Phase 1 (全部 6 Task) | Sprint 3 Task 8-5 | Beta 必须项筛选 |
| Phase 2 (全部 7 Task) | Sprint 3 Task 8-2/8-3/8-5 | 错误码/Trace/收尾 |
| Phase 3 (全部 6 Task) | Sprint 3 Task 8-5 (筛选) | 仅 Vitest CI |
| Phase 4 (全部 6 Task) | Sprint 3 Task 8-1 | arXiv 为主 |
| Phase 5 (全部 5 Task) | Sprint 3 Task 8-5 (筛选) | Runbook + Rollback |

---
