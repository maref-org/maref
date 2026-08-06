# Zenodo DOI 注册流程 — D1c 闸门 G1 替代方案

> **状态**: 待执行 (2026-06-27 准备)
> **目的**: arXiv ID 背书路径阻塞 (15 封邮件 0 合格)，Zenodo DOI 作为 STATE.yaml 指定的 backup academic identifier

## 已完成准备

- [x] `.zenodo.json` 元数据文件创建 (2026-06-27)
- [x] `CITATION.cff` 文件创建 (2026-06-27)
- [x] pyproject.toml version 同步 (`0.35.0-beta`)
- [x] LICENSE (Apache-2.0) 已就位

## 待用户执行步骤 (浏览器操作)

### 步骤 1: Zenodo 账号与 GitHub 集成

1. 访问 https://zenodo.org/login/ → 使用 GitHub 账号登录
2. 进入 https://zenodo.org/account/settings/applications/
3. 找到 GitHub 集成 → 启用 `maref-org/maref` 仓库授权

### 步骤 2: 创建 GitHub Release 触发 Zenodo webhook

```bash
# 在 public/maref 仓
git tag -a v0.35.0-beta -m "v0.35.0-beta — Phase 1 cleanup + coverage + gate hardening"
git push origin v0.35.0-beta

# 在 GitHub 网页创建 Release (基于上面的 tag)
# 标题: v0.35.0-beta
# 内容: 引用 CHANGELOG.md 中 v0.35.0-beta 章节
```

### 步骤 3: 获取 DOI 并写回

1. Release 创建后 1-5 分钟，Zenodo 会自动 mint DOI
2. 访问 https://zenodo.org/account/settings/github/ 查看
3. 把 DOI (格式如 `10.5281/zenodo.XXXXXXX`) 写回：
   - `STATE.yaml` → `submission_pipeline.arxiv_endorsement.zenodo_doi: "10.5281/zenod.XXXXXXX"`
   - `README.md` 顶部 badge 区域添加 `[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)`

### 步骤 4: 验证 D1c 闸门 G1

```bash
# 编辑 STATE.yaml 后验证
python3 scripts/d1_preflight_check.py
# 期望: G1_arxiv_id 仍 false, 但 zenodo_doi: "10.5281/zenodo.XXXXXXX" 提供替代学术标识
```

> **注意**: G1 闸门文字要求是 arXiv ID，Zenodo DOI 是 STATE.yaml 指定的 fallback。是否接受 DOI 替代 arXiv ID 推送，需人类审批。建议先注册 DOI，再决定是否调整 G1 闸门规则。

## 风险与替代

| 风险 | 应对 |
|------|------|
| Zenodo 服务波动 | 支持重新 mint，旧 DOI 仍有效 |
| 元数据错误 | Zenodo 网页可编辑已发布的版本（但会生成新 DOI） |
| GitHub release 包含专有文件 | pre-push hook 已保护，release 内容应自动过滤 |

## 后续

DOI 注册完成后，可向期刊投稿时引用此 DOI 作为软件可用性证据，反向推进 arXiv 背书（期刊接收 → arXiv 不需要 endorsement）。
