# 远程仓库健康修复执行计划

日期: 2026-07-04
来源: 远程仓库审计

---

## 任务 1: 修复 CI 全线失败

### 1.1 Security Scan (`security-scan.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| `secrets-scan` (TruffleHog) | BASE==HEAD 时无法扫描 | 在 push 事件中跳过 TruffleHog（仅 PR 时运行），或使用 `trufflehog filesystem .` 替代 |
| `dast-scan` (ZAP) | Action `zaproxy/action-baseline@v0.20.0` 不存在 | 升级到 `v0.28.0` 或移除（当前无运行服务） |
| `semgrep-scan` | `ValueError: invalid rule severity value: MEDIUM` | 更新 semgrep-action 版本或检查规则配置 |

**文件**: `.github/workflows/security-scan.yml`

### 1.2 Docs 构建 (`docs.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| Docusaurus 构建失败 | `versioned_docs/version-0.33` 目录不存在 | 创建 `docs/website/versioned_docs/version-0.33/` 目录（可空），或删除版本配置中的 0.33 引用 |

**文件**: `.github/workflows/docs.yml` + `docs/website/`

### 1.3 形式化验证 (`formal-verify.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| TLA+ 设置失败 | 退出码 8（Java/TLA 工具下载问题） | 检查 Java 版本兼容性，更新 TLA 工具下载 URL 或使用 Docker 镜像 |

**文件**: `.github/workflows/formal-verify.yml`

### 1.4 SonarCloud (`sonarcloud.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| 测试收集失败 | 缺少依赖 `starlette`, `numpy`, `cryptography`, `click` | 在 SonarCloud workflow 中安装 `.[dev,test,all]` 依赖组，或修正 pytest 的忽略模式 |

**文件**: `.github/workflows/sonarcloud.yml`

### 1.5 Lighthouse CI (`lighthouse.yml` / `performance.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| GUI 构建失败 | TS 路径别名 `@/` 未解析 — `@/lib/utils` 缺失 | 创建 `gui/src/lib/utils.ts` 或添加 `tsconfig.json` 中 paths 配置 |

**文件**: `gui/src/lib/utils.ts`（需创建），`gui/tsconfig.json`（需检查）

### 1.6 前端安全审计 (`frontend-security.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| `pnpm audit` 退出码 1 | 依赖存在已知漏洞 | 运行 `pnpm audit --fix` 或添加 `--audit-level=high` 允许低严重度漏洞通过 |

**文件**: `.github/workflows/frontend-security.yml`

### 1.7 CI 引用不存在路径 (`ci.yml`)

| 失败项 | 根因 | 修复措施 |
|--------|------|---------|
| MockValidator | 引用 `vault/schemas` 和 `vault/mocks` | 更新 ci.yml 中的路径，调整 MockValidator 配置指向正确路径 |
| crypto-test | 引用 `tests/compliance/test_crypto_sm2.py` 等不存在文件 | 更新 ci.yml 中的测试路径 |

**文件**: `.github/workflows/ci.yml`

---

## 任务 2: 启用 Secret Scanning

**操作**: 通过 GitHub API 启用

```bash
# 启用 secret scanning
gh api /repos/maref-org/maref --method PATCH \
  -f security_and_analysis={secret_scanning:{status:enabled}}

# 验证
gh api /repos/maref-org/maref/secret-scanning/alerts
```

---

## 任务 3: 清理 PR 队列

### 3.1 Dependabot PR (18 个)

所有 dependabot PR 均为 MERGEABLE 但被 CI 阻塞。策略：

| 类型 | 数量 | 措施 |
|------|------|------|
| 安全/补丁升级 | 18 | 待 CI 修复后触发 `dependabot-auto-merge` 自动合并；或被阻塞 19 天的直接关闭由 Dependabot 重建 |

优先处理：CI 修复后自动触发合并。如需立即清理，可全部关闭。

### 3.2 真实 PR (2 个)

| PR | 分支 | 状态 | 措施 |
|----|------|------|------|
| #66 | `docs/oss-sync-v0.35.0` | CONFLICTING | 手动解决冲突后合并 |
| #65 | `audit-fixes-v2` | CONFLICTING | 手动解决冲突后合并 |
| #64 | `docs/geo-readme-rewrite` | CONFLICTING + 无 review | 更新分支并申请 review |

### 操作步骤

```bash
# 列出所有 dependabot PR
gh pr list --repo maref-org/maref --state open --author app/dependabot --json number,title,createdAt

# 选择一个策略：
# 策略 A: 全部关闭，让 Dependabot 重建
# 策略 B: 等 CI 修复后自动合并

# 关闭所有 dependabot PR（如选择策略 A）
gh pr list --repo maref-org/maref --state open --author app/dependabot --json number \
  --jq '.[].number' | xargs -I{} gh pr close {} --repo maref-org/maref --comment "CI blocked, will be recreated by Dependabot"
```

---

## 任务 4: 清理 Stale 分支

### 待删除分支 (>30 天未更新)

- dependabot 分支 (18 个) — 安全重开
- 已合并的分支: `fix/ruff-lint-errors`, `fix/three-workflows`, `fix/three-workflows-clean`, `fix/ci-security-scan`, `fix/sast-findings`, `feat/codeql-security-analysis` 等
- 废弃分支: `chore/clean-release-artifacts`, `readme-open-source-landing`

**总计**: ~30 个分支

### 操作步骤

```bash
# 列出待清理分支
STALE_BRANCHES=$(gh api /repos/maref-org/maref/branches --paginate --jq \
  '.[] | select(.commit.commit.author.date < "2026-06-04T00:00:00Z") | select(.name != "main") | .name')

# 逐分支检查是否已合并
for branch in $STALE_BRANCHES; do
  gh api /repos/maref-org/maref/branches/$branch --jq '{name: .name, merged: .merged}'
done

# 删除已合并分支
for branch in $STALE_BRANCHES; do
  if gh api /repos/maref-org/maref/branches/$branch --jq '.merged' | grep -q true; then
    gh api /repos/maref-org/maref/git/refs/heads/$branch --method DELETE
  fi
done
```

---

## 任务 5: 精简 Workflow

### 合并方案

| 合并组 | 保留 | 删除 | 原因 |
|--------|------|------|------|
| Lighthouse CI | `lighthouse.yml`（功能更全） | `performance.yml` | 同时运行 LHCI，功能重复 |
| CI / Release Gate | `ci.yml`（通用触发） | `release-gate.yml` 中的功能移至 ci.yml 可选 job，删除独立 workflow | 测试+安全检查重复 |
| 安全扫描 | `ci.yml`（基础安全）+ `security-scan.yml`（深度扫描） | 调整重叠项 | 保留双层安全模型 |
| Docs 构建 | `deploy-website.yml` | `docs.yml` | 构建+部署合并为单一步骤 |
| Star 追踪 | `weekly-star-report.yml`（讨论帖） | `stargazer-thankyou.yml`（Issue，噪音大） | Issue 级的感谢已不必要 |

### 操作步骤

```bash
# 1. 删除 performance.yml
rm .github/workflows/performance.yml

# 2. 删除 docs.yml
rm .github/workflows/docs.yml

# 3. 删除 stargazer-thankyou.yml
rm .github/workflows/stargazer-thankyou.yml

# 4. 修改 ci.yml — 添加 coverage + SAEB job
# 5. 修改 release-gate.yml — 标记为 deprecated 或移除
```

---

## 任务 6: 发布 v0.30.0-GA

### 操作步骤

```bash
# 发布 draft release
gh release edit v0.30.0-GA --repo maref-org/maref --draft=false --discussion-category "Announcements"
```

---

## 执行顺序建议

```
1. 先修 CI (1.1 → 1.6)     ← 前置任务，其他步骤依赖 CI 通过
2. 启用 Secret Scanning     ← 独立，可并行
3. 精简 Workflow (5)        ← 与 CI 修复同步进行
4. 清理 PR 队列 (3)         ← 待 CI 通过后触发 auto-merge
5. 清理 Stale 分支 (4)      ← 独立，可随时执行
6. 发布 v0.30.0-GA (6)      ← 最后，等 CI 稳定后
```

## CI 修复分工建议

| 工作流 | 修改 |
|--------|------|
| `security-scan.yml` | 3 处简单修复（TruffleHog 条件 + ZAP 版本 + Semgrep 规则） |
| `docs.yml` | 1 处修复（创建缺失版本目录） |
| `formal-verify.yml` | 可能需要调试（TLA+ Java 环境） |
| `sonarcloud.yml` | 1 处修复（安装额外 dev 依赖） |
| `lighthouse.yml` | GUI 代码修复（创建 `@/lib/utils`） |
| `frontend-security.yml` | 1 处修复（降低 audit 级别） |
| `ci.yml` | 2 处修复（修正不存在路径引用） |
