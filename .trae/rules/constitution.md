# Constitution Rules for Trae AI — MAREF

## 上位法
本文件受 [Athena 系统宪法 v1.5](/Volumes/1TB-M2/public/CONSTITUTION.md) 约束。冲突时以宪法优先。

## 安全红线（Article 4-A，完整 6 条）
1. `git remote -v` 必须仅显示授权 remote
2. 禁止绕过 pre-push hook（`--no-verify`）
3. 禁止将 Athena 专有文件（SOUL.md / IDENTITY.md / .openclaw/ 等）提交到此仓库
4. 禁止 `gh` CLI 推送到非授权远程
5. CD pipeline（cd.yml）必须处于禁用状态
6. Agent 启动时必须验证 remote 为授权 remote

## 同步方向
A → B 单向（Athena 开发源 → GitHub 发布源）。所有变更必须在 Athena 开发源完成后再同步。

## 泄密预防
本仓库不得包含 T3/T2 级内容（路径/Key/IP/时间戳/依赖图）。发布前必须经过叙事转化引擎处理。

## 文档来源层级（Article 31-A）
- L0（权威源）: Athena知识库
- L1（代码配套）: public/maref/docs/
- L2（公开参考）: GitHub 公开仓库
优先级: L0 > L1 > L2
