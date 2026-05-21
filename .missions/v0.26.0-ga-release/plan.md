# MAREF v0.26.0 GA Release Engineering Implementation Plan

> 生成日期: 2026-05-19
> 基线版本: v0.26.0-rc
> 目标: GA Release (Production Ready)
> 状态: 工程补强 Phase 1~5 完成，进入 GA 发布冲刺

---

## 1. 当前状态评估

### 1.1 测试指标
| 指标 | 当前值 | 目标 | 状态 |
|------|--------|------|------|
| 测试总数 | 4,711 collected | - | 🟢 |
| 通过 | 4,703 | ≥ 4,700 | 🟢 |
| 失败 | 1 (desktop real, 需 macOS Accessibility) | 0 (排除环境依赖) | 🟡 |
| 跳过 | 8 | - | 🟢 |
| 覆盖率 | 80.31% | ≥ 70% | 🟢 |

### 1.2 CI/CD 流水线
| 工作流 | 状态 | 备注 |
|--------|------|------|
| CI (lint + typecheck + test + build) | 🟢 | 多平台矩阵 (ubuntu/macos × py3.10/3.11/3.12) |
| Release (PyPI + Tauri) | 🟢 | 含 macOS 签名公证配置 |
| Frontend Security | 🟢 | 新增 |
| Lighthouse CI | 🟢 | 新增 |
| Security Scan (bandit + safety + trivy) | 🟢 | 新增 |
| Formal Verify (TLA+) | 🟢 | 新增 |
| Performance | 🟢 | 新增 |
| Docker CI | 🟢 | 新增 (含 Trivy 镜像扫描) |

### 1.3 GA Release Checklist 完成度
| 项目 | 状态 | 备注 |
|------|------|------|
| CRITICAL/HIGH 安全漏洞修复 | ✅ | SAST/SCA 集成 CI |
| SLO 目标定义 | ✅ | 99.9% 可用性, P99 <500ms |
| 代码签名证书配置 | ✅ | CI secrets + 签名脚本 |
| macOS 公证凭证配置 | ✅ | CI workflow |
| Tauri Updater 配置 | ✅ | tauri.conf.json |
| 版本统一 | ✅ | 所有配置 → 0.26.0 |
| Core CI 绿色 | ✅ | 4,703 passed |
| 运维就绪文档 | ✅ | SLO.md, Runbook, 回滚脚本等 |
| **PRR re-audit score ≥ 9.0/10** | ❌ | **待执行** |
| **20 PRR 风险关闭/接受** | ❌ | **待执行** |
| **Docker build 验证** | ❌ | 工作流已就绪 |
| **Chaos 测试 (5/5)** | ❌ | **待执行** |
| **24h 稳定性测试** | ❌ | 脚本就绪未运行 |
| **端到端验证循环** | ❌ | **待执行** |
| **跨平台验证** | ❌ | macOS 14+, Windows 11, Ubuntu 22.04 |
| **Git tag + Release** | ❌ | **待执行** |
| **Docker image push** | ❌ | **待执行** |
| **包分发 (dmg/msi/AppImage)** | ❌ | **待执行** |

---

## 2. Phase 6: GA 发布冲刺 (本周)

### 2.1 工程补强完成项 (Phase 1~5)
以下为 v0.26.0 已完成的工程补强工作：

#### P0 阻塞器修复
- [x] 覆盖率报告全零问题 — 移除过度 omit 配置
- [x] CSP `unsafe-inline` 安全漏洞 — nonce 策略
- [x] Git tag 版本不一致 — v0.9.0-rc → v0.26.0
- [x] CHANGELOG 内容缺失 — 完整版本历史

#### GUI 流式渲染基础
- [x] SSE 流式管道端到端分析 (backend → hook → store → UI)
- [x] TokenUsage 组件集成到 StatusBar
- [x] MessageBubble 流式 Token 计数指示器
- [x] 开发日志 trace_id 关联

#### 安全基础设施
- [x] 7 个 CI 安全工作流
- [x] CSP nonce 策略
- [x] Secret 检测脚本
- [x] Trivy 文件系统/镜像扫描
- [x] bandit SAST 集成

#### 可观测性基础
- [x] OpenTelemetry 中间件 (全请求追踪)
- [x] RED 指标收集器 (QPS, 错误率, P50/P95/P99)
- [x] Trace 上下文传播 (ContextVar)
- [x] 结构化日志集成 (structlog + trace_id)

#### 运维就绪
- [x] Docker 多阶段构建 (non-root, healthcheck)
- [x] K8s HPA 配置
- [x] 5+ Runbooks
- [x] 回滚脚本
- [x] Go/No-Go 决策模板
- [x] 部署文档

---

## 3. 剩余工作项

### 优先级 P0 (GA 阻塞器)

#### P0-1: PRR 重新审计
- **描述**: 执行 PRR re-audit，目标评分 ≥ 9.0/10
- **检查项**:
  - 所有 20 PRR 风险逐项确认状态 (closed/accepted)
  - 审计证据收集 (测试报告、覆盖率报告、安全扫描报告)
  - 生成 PRR re-audit 报告
- **验收标准**: re-audit score ≥ 9.0/10
- **依赖**: 所有 P0 修复完成

#### P0-2: Chaos 测试验证
- **描述**: 5/5 故障类型全部通过
- **故障类型**:
  1. OOM (内存耗尽)
  2. 文件锁竞争
  3. 磁盘 IO 压力
  4. 网络分区/延迟
  5. 子进程异常退出
- **命令**: `pytest tests/chaos/ -v --chaos`
- **验收标准**: 5/5 故障类型通过

#### P0-3: 24h 稳定性测试
- **描述**: 验证内存增长 < 5%
- **命令**: `python scripts/benchmark_memory.py --duration 24h`
- **验收标准**: 24h 后内存增长 < 5%

#### P0-4: 端到端验证
- **描述**: screenshot → parse → operate → verify 完整闭环
- **场景**:
  1. 打开应用 → 截图 → 解析 UI → 点击按钮 → 验证结果
  2. 读取代码文件 → 修改 → 保存 → 验证
  3. 运行测试 → 解析结果 → 报告
- **验收标准**: 3/3 场景通过

### 优先级 P1 (发布关键)

#### P1-1: 跨平台验证
| 平台 | 构建 | 安装 | 功能测试 |
|------|------|------|----------|
| macOS 14+ (arm64) | ✅ | ❌ | ❌ |
| macOS 14+ (x64) | ✅ | ❌ | ❌ |
| Windows 11 | ✅ | ❌ | ❌ |
| Ubuntu 22.04 | ✅ | ❌ | ❌ |

#### P1-2: Docker 镜像发布
- [ ] 注册 Docker Hub / GHCR 仓库
- [ ] 配置 CI 推送凭证
- [ ] 验证 docker.yml 推送步骤

#### P1-3: 包分发
- [ ] macOS: DMG 签名 + 公证
- [ ] Windows: MSI 签名
- [ ] Linux: AppImage 构建

#### P1-4: GitHub Release
- [ ] Git tag: `v0.26.0`
- [ ] Release notes 自动生成 (from CHANGELOG)
- [ ] 上传构建产物

### 优先级 P2 (质量持续提升)

#### P2-1: GUI 构建验证
- [ ] `pnpm build` 通过
- [ ] 无 TypeScript 错误
- [ ] 包体积优化

#### P2-2: 覆盖率持续提升
| 模块 | 当前 | 目标 |
|------|------|------|
| 整体 | 80.31% | ≥ 85% |
| 核心治理 | ~85% | ≥ 90% |
| Sidecar | ~65% | ≥ 80% |
| Desktop | ~55% | ≥ 75% |

#### P2-3: 文档完善
- [ ] API 文档同步
- [ ] 用户手册 (快速开始)
- [ ] 架构文档更新

---

## 4. 时间线与里程碑

```
Phase 6: GA 发布冲刺 (5天)
├── Day 1: PRR 重新审计 + Chaos 测试
│   ├── P0-1: PRR re-audit
│   └── P0-2: Chaos 5/5
├── Day 2: 稳定性 + 端到端验证
│   ├── P0-3: 24h 稳定性测试 (启动)
│   └── P0-4: 端到端验证
├── Day 3: 跨平台 + Docker 发布
│   ├── P1-1: 跨平台验证
│   ├── P1-2: Docker 镜像推送
│   └── P1-3: 包签名/分发
├── Day 4: Release + 文档
│   ├── P1-4: GitHub Release
│   └── P2-3: 文档完善
└── Day 5: Go/No-Go 决策 + 发布
    ├── P2-1: GUI 构建验证
    └── GA Release Go/No-Go
```

### 里程碑
| 里程碑 | 截止 | 交付物 |
|--------|------|--------|
| M1: PRR Re-Audit Pass | Day 1 | re-audit 报告, score ≥ 9.0 |
| M2: 质量门禁 | Day 2 | Chaos 5/5, 24h 稳定, E2E 通过 |
| M3: 发布就绪 | Day 3-4 | 跨平台包, Docker image, GitHub Release |
| M4: GA Release | Day 5 | Go/No-Go 决策, 正式发布 |

---

## 5. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| PRR re-audit < 9.0 | 低 | 高 | 提前逐项核对，预留缓冲日 |
| Chaos 测试发现新故障 | 中 | 中 | 已有故障注入框架，修复周期 < 4h |
| 24h 稳定性内存泄漏 | 低 | 高 | 已有 benchmark 脚本，早期发现 |
| 跨平台构建环境问题 | 中 | 中 | CI 矩阵已验证构建通过 |
| macOS 公证延迟 | 中 | 低 | 提前提交，12h 内通常完成 |

---

## 6. 决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| Docker registry | Docker Hub / GHCR | 双推 | 冗余 + 国内加速 |
| Release 策略 | 滚动 / 蓝绿 | 蓝绿部署 | K8s 已配置 HPA + readiness |
| 版本号方案 | semver / calver | semver | v0.26.0 → v1.0.0 |
| 分布渠道 | GitHub Releases only | 暂定 | 减少维护成本 |

---

## 7. 回滚预案

如果 Go/No-Go 决策为 No-Go:
1. 记录 No-Go 理由到决策模板
2. 制定补强计划 (预计 1-3 天)
3. 重新安排 Go/No-Go 评审

如果 GA Release 后发现严重问题:
1. 执行 `scripts/rollback.sh` 回滚 K8s 部署
2. 在 GitHub Release 标记为 "Pre-release"
3. 发布 hotfix 版本 v0.26.1