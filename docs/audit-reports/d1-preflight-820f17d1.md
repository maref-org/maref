# D1 Pre-Flight 记录 — main@820f17d1

- 执行时间: 2026-10-26T07:26:07Z
- 目标: maref-org/maref@main `820f17d10c42df1952287ff8c101fb6cca1fe0a5`
- 命令: `python3 scripts/d1_preflight_check.py --sha 820f17d10c42df1952287ff8c101fb6cca1fe0a5`
- 执行环境: 维护者本机（与 `.githooks/pre-push` 同一脚本）

## 结果

| 闸门 | 结果 | 证据 |
|------|------|------|
| G1 Branch Protection | 通过 | 10 contexts，10 required |
| G2 CI Status | 通过 | 6 个必需 check-runs 成功 |
| G3 Security Scan | 通过 | Security Scan run 40283282916 (success) |
| G4 No Runtime Artifacts | 通过 | 索引中无运行时产物 |

退出码: `0`（全部通过）

## 关联运行

| 工作流 | run ID | 完成时间 | 结论 |
|--------|--------|----------|------|
| MAREF CI | 40283282776 | 2026-10-26T07:25:56Z | success |
| Security Scan | 40283282916 | 2026-10-26T07:03:36Z | success |
| Dependency Audit | 40283282879 | 2026-10-26T07:02:27Z | success |

## 运行时证言

- 证言 ref: `attestations/latest` @ `b9f2e220162112b91ec70cdd3d19fcd82dd26769`
- 验证: `verify_runtime_attest.py --public-key configs/runtime-attest-public.pub --require-healthy`
- 结果: `verified=true`，`key_id=1c650ce065489fd165f20cc14c948a29`，age 10077.6s（<24h），m0–m4 全为 true

## 说明

本记录为 D1 闸门的可追溯证据，对应 `STATE.yaml` 中 `d1_gate.value: passed`。main 分支保护要求所有变更经 PR，因此该证据随合并后的 STATE.yaml 指针更新一并提交。
