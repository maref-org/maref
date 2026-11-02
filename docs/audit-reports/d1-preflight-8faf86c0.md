# D1 Pre-Flight 记录 — main@8faf86c0（v0.55.2 tag 基线）

- 执行时间: 2026-11-01T13:04:39Z（本机复验）；2026-11-01T14:25:59Z（pre-push 复验）
- 目标: maref-org/maref@main `8faf86c0f667a22dd3cbf577ac9b63a2289c0807`（PR #500 合并后）
- 命令: `python3 scripts/d1_preflight_check.py --sha 8faf86c0f667a22dd3cbf577ac9b63a2289c0807`
- 执行环境: 维护者本机（与 `.githooks/pre-push` 同一脚本）
- 用途: `v0.55.2` tag 推送前的 D1c 闸门判定

## 结果

| 闸门 | 结果 | 证据 |
|------|------|------|
| G1 Branch Protection | 通过 | 10 contexts，10 required |
| G2 CI Status | 通过 | 6 个必需 check-runs 成功（lint/test/security/crypto-test/chaos-test/sca） |
| G3 Security Scan | 通过 | Security Scan run 41307080936 (success) |
| G4 No Runtime Artifacts | 通过 | 索引中无运行时产物 |

退出码: `0`（两次执行均全部通过）

## 关联运行（main@8faf86c0 push）

| 工作流 | run ID | 结论 |
|--------|--------|------|
| MAREF CI | 41307080946 | success（12:33:47Z→12:53:38Z） |
| Security Scan | 41307080936 | success |
| Dependency Audit | 41307080942 | success |
| CodeQL | 41307080953 | success |
| SonarCloud Scan | 41307080932 | success |
| Docker CI | 41307080990 | success |
| Leak Detection | 41307080971 | success |

## 覆盖率

- CI run 41307080946 产物 `coverage-8faf86c0...`：72772/91748 行，综合 76.50%（含分支），分支 15185/23226 = 65.38%。
- 产物已下载本地解析核对，见 `STATE.yaml` 的 `coverage` 节点。

## 说明

本记录为 `v0.55.2` tag 推送前的 D1 闸门证据，对应 `STATE.yaml` 中 `d1_gate.value: passed`。
