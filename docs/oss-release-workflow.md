# MAREF 开源发布工作流（OSS Release Workflow）

> **状态**: v1.0（2026-08-06）
> **上位法**: [OSS 执行规范 v1.0](oss-execution-norm-v1.0.md) · AGENTS.md · MAREF 战略文档 §13
> **范围**: `maref-org/maref` 公开仓的发布纪律。所有 Code Agent 与维护者必须遵守。

---

## 1. 核心规则（铁律）

| # | 规则 | 说明 |
|---|------|------|
| R-OSS-1 | **`dev`/`main` 全仓分支禁止直接推送公开 remote** | 本地 `dev` 含闭源王炸层（联邦深水区/供应链/数据湖），裸推即护城河归零。pre-push 门禁会阻断，请勿 `--force` 绕过 |
| R-OSS-2 | **公开发布一律走 `scripts/oss-publish.sh --push`** | 脚本按 `scripts/oss-exclude-list.txt` 裁剪 → 重建 `oss-release` 分支 → 复核 → 推送 |
| R-OSS-3 | **`oss-release` 分支与 `*-oss` tag 是唯一公开发布产物** | 其他分支/标签不得推送到公开 remote |
| R-OSS-4 | **`*,cover` 文件永不提交** | Python `trace --coverdir` 的过期源码快照，含旧实现，已 `.gitignore` |
| R-OSS-5 | **新增深水区实现必须同步登记 `oss-exclude-list.txt`** | 否则 pre-push 门禁不会自动识别，存在误推风险 |

---

## 2. 工具链

| 文件 | 作用 |
|------|------|
| `scripts/oss-exclude-list.txt` | 闭源/敏感路径清单（密钥/数据/深水区/未来守卫） |
| `scripts/oss-check.sh <treeish>` | 门禁校验：tree 是否含排除路径；命中 → exit 1 |
| `scripts/oss-publish.sh [--push]` | 裁剪发布流水线（重建 oss-release + 提交 + 复核 + 推送） |
| `.githooks/pre-push` | 推送门禁（安装：`scripts/install-hooks.sh`） |
| `scripts/oss-filter-history.sh` | 一次性历史清理（filter-repo 剔除深水区，见 §4） |

---

## 3. 标准发布流程

### 3.1 发布

```bash
cd <MAREF_REPO_ROOT>

# 预检（可选）：dry-run 查看将裁剪哪些路径
bash scripts/oss-publish.sh --dry-run

# 正式发布：重建 oss-release + 推送到 origin + 打 <版本>-oss tag
bash scripts/oss-publish.sh --push
```

发布产物：
- 分支 `origin/oss-release`
- tag `origin/<pyproject版本>-oss`（如 `0.52.0-oss`）

> **孤儿根提交机制**: `oss-publish.sh` 用 `git checkout --orphan` 重建 oss-release——发布产物是**无父提交的单根提交**，绝不继承全仓历史，从机制上杜绝深水区历史回流（2026-08-06 修复）。脚本内部 commit 使用 `--no-verify`（pre-commit 对测试假密钥的误报不阻断发布，门禁由 `oss-check.sh` 把关）。

### 3.2 发布后

- 在 GitHub 用 `oss-release` 分支发起 PR 合并到 `main`（或配置 `main` 允许 oss-release 直接合并），使 `main` 与最新公开版同步。
- 更新 `docs/oss-todo.md`、`CHANGELOG.md`（裁剪版 CHANGELOG）。

### 3.3 本地迭代不发布

本地开发、测试、提交均在 `dev` 全仓分支进行，**不需要也不应该推公开 remote**。发布是显式动作。

---

## 4. 一次性历史清理（filter-repo）

> **触发条件**: 正式对外宣传/融资/大范围分发前。当前公开仓 `main`/`dev` 历史仍含旧版全仓（深水区残留），git 历史可被扒取。
> **警告**: 该操作改写全部 commit hash，会 invalidate 所有 fork/PR/CI badge。确认无活跃协作者后再执行。

步骤：

```bash
# 1) 完整备份（本地 + 远程 tag/branch 列表）
cp -r <MAREF_REPO_ROOT> <MAREF_REPO_ROOT>-backup-$(date +%Y%m%d)
git remote add backup-origin git@github.com:maref-org/maref 2>/dev/null || true

# 2) 安装 git-filter-repo
pip install git-filter-repo

# 3) 在临时克隆上清理（不在工作仓直接跑，避免破坏工作区）
git clone <MAREF_REPO_ROOT> /tmp/maref-filter && cd /tmp/maref-filter
git checkout -b filter-run origin/main

# 4) 剔除深水区/敏感路径（路径清单见 scripts/oss-exclude-list.txt，逐条 --path 传入）
bash <MAREF_REPO_ROOT>/scripts/oss-filter-history.sh

# 5) 校验清理结果：历史中不再出现深水区文件
git log --all --oneline -- src/maref/recursive/distributed_crdt.py | head   # 应为空
git log --all --oneline -- .missions | head                                 # 应为空

# 6) 覆盖推送到公开 remote（force，需确认）
git push origin --force --all
git push origin --force --tags

# 7) 后续全仓内容只存在本地 dev 私有分支；公开仓仅保留干净历史
```

> **注意**: 本地 `dev`（全仓）与公开仓（干净历史）将从此分叉。公开仓后续只接收 `oss-publish.sh` 裁剪产物。若希望公开仓 `main` 始终保持干净，可只推送 `oss-release`/`main`（裁剪链），**永不推送本地 dev 到公开 remote**。

### 已执行记录（2026-08-06）

1. 备份镜像 `maref-mirror-20260806.git`（641M，217 refs）→ 外置盘 `backups/maref/`
2. 临时克隆执行 filter-repo：381 → 367 commits，`.missions/experiments/*.cover/深水区/密钥`历史归零（`.env.example` 按策略保留公开）
3. 公开 remote 删除 **154** 个含深水区分支（`dev`/`dependabot/*`/`feat/*`/`fix/*`/`improvement/*`/`release/*`/`sync/*`）
4. force 推送干净 `main`（a579238）+ 全部 26 个 tags
5. 恢复分支保护：`main`（PR+禁force）`oss-release`（禁删+允许force）

### 已知限制（refs/pull/*）

filter-repo 无法清理 GitHub 平台层的 `refs/pull/*` 引用（300+ PR 历史快照仍可能含深水区）。普通 `git clone` **不会**拉取这些引用，仅显式 `git fetch origin pull/<N>/head` 才能访问。如需彻底清除须联系 GitHub 支持或批量关闭/归档 PR（破坏性）。

---

## 5. 远程分支保护设置（建议）

在 GitHub Settings → Branches → Branch protection rules：

| 分支 | 保护规则 |
|------|----------|
| `main` | Require PR before merging（≥1 approve）；Require status checks（CI 门禁）；enforce_admins=true；禁止 force push |
| `oss-release` | 仅 maintainer 可写；enforce_admins=true；禁止删除；**允许 force push（唯一例外，供受控发布脚本 `scripts/oss-publish.sh --push` 重建孤儿根）** |
| `dev` | 不建议在公开 remote 保留（全仓）。若保留则设为 Private 或删除 |

推荐用 `gh` CLI 一键设置（见 `scripts/setup-branch-protection.sh`，需先 `gh auth login`）。

---

## 6. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-08-06 | 初始版：发布纪律、工具链、filter-repo 步骤、保护建议 |
