# GitHub Agent 自动化操作规范

> **Repository**: `frankiehot-tech/Athena`（私有）· `maref-org/maref`（公开）  
> **Purpose**: AI Agent 自动化操作 GitHub 的安全规范  
> **Last Updated**: 2026-06-05  
> **Version**: 1.3.0

---

## 0. 仓库分类

| 仓库 | 可见性 | 用途 | 适用规则 |
|------|--------|------|----------|
| `frankiehot-tech/Athena` | 私有 | Athena 私有代码 | 全部规则（含 PRIVATE_REPO_RULES.md） |
| `maref-org/maref` | 公开 | MAREF 开源发布 | 全部规则 + 额外公开仓库限制 |

> **冲突解决**: 若与 PRIVATE_REPO_RULES.md 冲突，以本文件为准。

---

## 1. 权限分级系统

### 1.1 权限级别定义

| 级别 | 名称 | 可执行操作 | 风险等级 |
|------|------|-----------|---------|
| L1 | 只读 | 查看仓库、Issues、PR、Wiki | 低 |
| L2 | 内容写入 | 创建/修改文件、提交 commit | 中 |
| L3 | PR 管理 | 创建 PR、添加标签、评论 | 中 |
| L4 | 仓库管理 | 管理分支保护、Webhooks、Secrets | 高 |
| L5 | 危险操作 | 删除仓库、转移所有权、强制推送 | 极高 |

### 1.2 Agent 默认权限

- **默认级别**: L2（内容写入）
- **需人工审批**: L4 及以上操作
- **禁止操作**: 删除分支、强制推送、修改仓库可见性

---

## 2. 操作红线

### 2.1 绝对禁止

- ❌ 删除任何分支（包括已合并的 feature 分支）
- ❌ 强制推送 (`git push --force`)
- ❌ 修改或移除分支保护规则
- ❌ 删除或覆盖 Secrets/环境变量
- ❌ 修改 CODEOWNERS 文件
- ❌ 删除 Releases 或 Tags
- ❌ 转移仓库所有权

### 2.2 需人工审批

- ⚠️ 创建新的 workflow 文件
- ⚠️ 修改 `.github/dependabot.yml`
- ⚠️ 添加或删除 GitHub App 集成
- ⚠️ 修改仓库描述/主页/话题
- ⚠️ 发布新版本 Release

### 2.3 允许自主操作

- ✅ 修改文档文件 (`.md`)
- ✅ 修复代码 typo
- ✅ 创建 feature 分支并提交
- ✅ 创建 Pull Request
- ✅ 回复 Issue 评论

---

## 3. 仓库识别协议

### 3.1 目标仓库识别

Agent 操作前必须确认：

```bash
# 1. 确认当前仓库
git remote get-url origin

# 2. 确认当前分支
git branch --show-current

# 3. 确认工作区状态
git status
```

### 3.2 仓库分类检测

```bash
# 检测仓库可见性
REPO_INFO=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY")
VISIBILITY=$(echo "$REPO_INFO" | jq -r '.visibility')

if [ "$VISIBILITY" = "private" ]; then
  echo "私有仓库 - 应用全部规则"
else
  echo "公开仓库 - 应用全部规则 + 额外公开限制"
fi
```

---

## 4. Action 白名单

### 4.1 官方 Action（允许使用 @v 标签）

```yaml
# 官方 Action
- actions/checkout@v4
- actions/setup-python@v5
- actions/setup-node@v4
- actions/cache@v4
- actions/upload-artifact@v4
- actions/download-artifact@v4
- actions/create-github-app-token@v1
```

### 4.2 安全扫描（允许使用 @v 标签）

```yaml
# 安全扫描
- github/codeql-action@v3
- trufflesecurity/trufflehog@v3
- returntocorp/semgrep-action@v1
- aquasecurity/trivy-action@v0.36.0
- zaproxy/action-baseline@v0.14.0
- anchore/sbom-action@v0
```

### 4.3 代码质量（允许使用 @v 标签）

```yaml
# 代码质量
- coveragepy-linter/coveragepy-linter@v1
- chartboost/ruff-action@v1
- SonarSource/sonarcloud-github-action@v3
```

### 4.4 构建与发布（必须使用 SHA 锁定）

```yaml
# 构建与发布（SHA 锁定）
- pypa/gh-action-pypi-publish@9fd53255263d9c38e8f0c6f5e8e7c9c1d5e0e5c6
- softprops/action-gh-release@v2
- docker/setup-buildx-action@v3
- docker/metadata-action@v5
- docker/build-push-action@v6
- docker/login-action@v3
- pnpm/action-setup@v3
- dtolnay/rust-toolchain@stable
```

### 4.5 禁止使用的 Action

- ❌ 任何未在此白名单中的第三方 Action
- ❌ 使用 `@master`、`@main`、`@latest`、`@stable` 动态标签的 Action
- ❌ 来源不明的 Action（检查发布者是否为组织/已验证用户）

---

## 5. Workflow 权限声明

### 5.1 最小权限原则

每个 workflow **必须**在顶层声明 `permissions` 字段：

```yaml
# 只读权限（默认）
permissions: read-all

# 或明确指定
permissions:
  contents: read
  pull-requests: write
  issues: read
```

### 5.2 权限对照表

| 操作 | 所需权限 |
|------|---------|
| 读取代码 | `contents: read` |
| 提交代码 | `contents: write` |
| 创建 PR | `pull-requests: write` |
| 创建 Issue | `issues: write` |
| 上传 Artifact | `actions: write` |
| 发布 Release | `contents: write` |

---

## 6. 依赖管理

### 6.1 Dependabot 配置

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      dev-dependencies:
        patterns:
          - "pytest*"
          - "ruff"
          - "mypy"
      production-dependencies:
        patterns:
          - "*"
        exclude-patterns:
          - "pytest*"
          - "ruff"
          - "mypy"
```

### 6.2 版本锁定

- 生产依赖：锁定具体版本 (`==1.2.3`)
- 开发依赖：允许小版本更新 (`~=1.2`)

---

## 7. 安全扫描

### 7.1 必需扫描

| 扫描类型 | 工具 | 触发时机 |
|---------|------|---------|
| 密钥扫描 | TruffleHog | 每次 push |
| 静态分析 | Semgrep | 每次 PR |
| 依赖漏洞 | Trivy | 每次 push |
| DAST | OWASP ZAP | 夜间定时 |
| 代码质量 | CodeQL | 每次 PR |

### 7.2 扫描失败处理

- **密钥泄露**: 立即撤销密钥，通知安全团队
- **高危漏洞**: 阻止合并，创建修复 Issue
- **中危漏洞**: 允许合并，限期 7 天修复
- **低危漏洞**: 记录，定期批量修复

---

## 8. PR 流程合规

### 8.1 PR 要求

- ✅ 标题格式: `类型 (模块): 描述`
- ✅ 包含变更描述和测试说明
- ✅ 通过所有 CI 检查
- ✅ 至少 1 个 CODEOWNERS 审批

### 8.2 CODEOWNERS

```
# .github/CODEOWNERS
# 默认所有者
* @frankiehot

# Python 源码
/src/maref/ @frankiehot
/src/maref_lite/ @frankiehot

# CI/CD
/.github/workflows/ @frankiehot
```

---

## 9. 仓库画像审计

### 9.1 审计维度

| 维度 | 指标 | 风险阈值 |
|------|------|---------|
| 贡献者分布 | 贡献者数量 | < 2 人 |
| 贡献集中度 | Top 1 占比 | > 80% |
| 组织透明度 | 公开成员数 | 0 人 |
| 社区健康度 | Stars/Forks | 0/0 |
| 文档完整性 | 关键文档 | 缺失 > 2 |
| 命名一致性 | 项目名称 | 不一致 |

### 9.2 审计频率

- **自动审计**: 每周一 UTC 4:00（通过 repo-audit.yml）
- **手动审计**: 运行 `./scripts/repo-audit.sh`

### 9.3 审计报告

审计结果应包含：

```
=== 仓库审计报告 ===
生成时间: 2026-06-05 04:00:00 UTC
仓库: maref-org/maref

审计维度:
- 贡献者分布和集中度
- 组织透明度
- 社区健康度
- 文档完整性
- 安全配置
- Action 版本锁定

发现问题:
- [警告] 单一贡献者风险
- [警告] 组织透明度风险
- [错误] CODEOWNERS 缺失
```

---

## 11. 邮件监听规范

### 11.1 支持的邮箱

| 邮箱 | 提供商 | IMAP 服务器 | 用途 |
|------|--------|------------|------|
| `frankiehot@hotmail.com` | Hotmail/Outlook | outlook.office365.com:993 | 主要监听 |
| `athenabot@qq.com` | QQ 邮箱 | imap.qq.com:993 | 备用监听 |
| `87909004@qq.com` | QQ 邮箱 | imap.qq.com:993 | arXiv + GitHub |

### 11.2 安全要求

- **必须使用 App Password/授权码**，禁止使用登录密码
- 密码存储位置：环境变量 或 macOS Keychain，禁止硬编码
- 邮箱配置见 `.env.example`，实际配置保存在 `.env`（已在 .gitignore 中）

### 11.3 邮件监听流程

```
GitHub 通知邮件 → IMAP 轮询 → 邮件解析 → 意图识别 → 自动/审批响应 → 执行仓库操作
```

### 11.4 自动操作白名单

| 操作类型 | 条件 | 审批要求 |
|---------|------|---------|
| 查看 PR/Issue 信息 | 任何通知 | 无需审批 |
| 合并 Dependabot PR | `AUTO_MERGE_DEPENDABOT=true` | 无需审批 |
| 重启失败 Workflow | `AUTO_RESTART_WORKFLOWS=true` | 无需审批 |
| 关闭过期 Issue | `AUTO_CLOSE_STALE_DAYS>0` | 无需审批 |
| 合并非 Dependabot PR | 任何情况 | 需要审批 |
| 推送代码 | 任何情况 | 需要审批 |
| 删除分支/Tag | 任何情况 | 禁止自动执行 |

### 11.5 相关文件

| 文件 | 用途 |
|------|------|
| `src/maref/tools/github_email_listener.py` | IMAP 监听器 |
| `src/maref/tools/github_email_parser.py` | 邮件解析器 |
| `src/maref/tools/github_email_responder.py` | 自动响应器 |
| `scripts/github-email-agent.py` | 主入口脚本 |
| `.github/workflows/github-email-listener.yml` | CI/CD 工作流 |

### 11.6 配置示例

```bash
# 启动持续监听
python scripts/github-email-agent.py

# 单次轮询（测试用）
python scripts/github-email-agent.py --once

# Dry run 模式
python scripts/github-email-agent.py --dry-run --verbose

# 查看统计
python scripts/github-email-agent.py --stats
```

---

## 12. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-06-04 | 初始版本 |
| 1.1.0 | 2026-06-04 | 添加仓库分类、更新 Action 白名单 |
| 1.2.0 | 2026-06-05 | 添加仓库画像审计章节 |
| 1.3.0 | 2026-06-05 | 添加邮件监听规范 |
| 1.4.0 | 2026-06-05 | 补全 CODEOWNERS、permissions、dependabot groups |
