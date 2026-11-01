# D1 Pre-Flight 记录 — main@234c52cf（v0.55.2 发布基线）

- 执行时间: 2026-11-01T09:39:35Z
- 目标: maref-org/maref@main `234c52cf9436ba193fb361e3dca48d0b3dc84715`（PR #499 合并后）
- 命令: `python3 scripts/d1_preflight_check.py --sha 234c52cf9436ba193fb361e3dca48d0b3dc84715`
- 执行环境: 维护者本机（与 `.githooks/pre-push` 同一脚本）
- 用途: `v0.55.2` tag 推送前的 D1c 闸门判定

## 结果

| 闸门 | 结果 | 证据 |
|------|------|------|
| G1 Branch Protection | 通过 | 10 contexts，10 required |
| G2 CI Status | 通过 | 6 个必需 check-runs 成功（lint/test/security/crypto-test/chaos-test/sca） |
| G3 Security Scan | 通过 | Security Scan run 41286696516 (success) |
| G4 No Runtime Artifacts | 通过 | 索引中无运行时产物 |

退出码: `0`（全部通过）

## 关联运行

| 工作流 | run ID | 结论 |
|--------|--------|------|
| MAREF CI | 41286696518 | success |
| Security Scan | 41286696516 | success |
| Dependency Audit | 41286696582 | success |
| CodeQL | 41286696570 | success |

## 覆盖率

- CI run 41286696518 产物 `coverage-234c52cf...`：72771/91748 行，综合 76.50%（含分支），分支 15184/23226 = 65.38%。
- 产物已下载本地解析核对，见 `STATE.yaml` 的 `coverage` 节点。

## 说明

本记录为 `v0.55.2` 发布前的 D1 闸门证据，对应 `STATE.yaml` 中 `d1_gate.value: passed`。
