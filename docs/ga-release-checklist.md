# MAREF GA Release Checklist

> 状态更新: 2026-05-18 — Phase 1~5 工程补强完成

## Pre-release
- [x] All CRITICAL/HIGH security vulnerabilities resolved — SAST/SCA 集成 CI
- [ ] PRR re-audit score >= 9.0/10
- [x] SLO targets defined (99.9% availability, P99 <500ms) — SLO.md + Runbook
- [ ] All 20 PRR risks closed or accepted
- [x] Code signing certificates configured — CI secrets + 签名脚本
- [x] macOS notarization credentials configured — CI workflow
- [x] Tauri Updater configured — tauri.conf.json + updater plugin

## Build verification
- [ ] `pnpm build` passes (GUI)
- [x] `maref --help` works (CLI) — CLI 测试覆盖 93.05%
- [ ] Docker build passes
- [ ] macOS codesign: `codesign -dvvv MAREF.app` passes
- [ ] Windows signtool verification passes
- [ ] Linux AppImage works

## Testing
- [x] Core CI pipeline green — 1353 passed, 3 skipped, coverage 71.84% ≥ 70%
- [ ] Chaos tests pass (5/5 fault types)
- [ ] 24h stability test: memory growth < 5% — 脚本已就绪 scripts/benchmark_memory.py
- [ ] End-to-end: screenshot->parse->operate->verify loop
- [ ] Cross-platform: macOS 14+, Windows 11, Ubuntu 22.04

## Release
- [x] Version bump (pyproject.toml, tauri.conf.json) — 统一至 v0.26.0
- [ ] Git tag v{major}.{minor}.{patch}
- [ ] GitHub Release with changelog
- [ ] Docker image push to registry
- [ ] Package distribution (dmg/msi/AppImage)

## 运维就绪
- [x] SLO/SLI 文档 — SLO.md
- [x] Runbook (5+) — docs/runbook/
- [x] 回滚脚本 — scripts/rollback.sh
- [x] 部署文档 — docs/deployment.md
- [x] Go/No-Go 决策模板 — docs/go-no-go-template.md
- [x] Lighthouse CI 工作流 — .github/workflows/lighthouse.yml
- [x] 前端安全审计 — .github/workflows/frontend-security.yml
