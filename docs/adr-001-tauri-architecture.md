# ADR-001: 桌面端架构决策 — Tauri-only

**状态**: 已接受
**日期**: 2026-05-14
**决策者**: MAREF 架构组

## 背景

MAREF GUI 当前维护两套桌面壳：Tauri (Rust) 和 Electron (Node.js)。双壳导致：

1. **维护成本翻倍**：两份构建配置、两份安全策略、两份依赖管理
2. **安全策略分歧**：Tauri CSP=null（已修复）vs Electron hardenedRuntime=false（已修复）
3. **功能碎片化**：部分功能只在 Tauri 实现（pet window），部分只在 Electron（构建签名）

## 决策

**采用 Tauri 2.x 作为唯一桌面壳，废弃 Electron。**

### 理由

| 维度 | Tauri | Electron | 胜出 |
|------|-------|----------|------|
| 包体积 | ~5MB | ~150MB | Tauri |
| 内存占用 | ~30MB | ~200MB | Tauri |
| Rust 安全 | 内存安全 + 系统 API | Node.js C++ 原生 | Tauri |
| CSP 控制 | tauri.conf.json 原生 | helmet 第三方 | Tauri |
| 自动更新 | tauri-plugin-updater | electron-updater | 平手 |
| 开发生态 | 较小，但成熟 | 最大 | Electron |
| macOS 签名 | 标准流程 | hardenedRuntime 需配置 | 平手 |

Tauri 在安全、性能、包体积三个维度碾压 Electron，且 MAREF 的核心治理能力（Rust 侧）天然适合 Tauri 的 Rust 后端。

### 后果

- **正面**：单一构建配置、统一安全策略、更小的安装包
- **负面**：失去 Electron 的庞大社区生态，部分 Node.js 原生模块需迁移至 Rust
- **迁移路径**：Electron 配置保留但标记为 DEPRECATED，v0.26.0 移除

## 实施检查项

- [x] 修复 Tauri CSP（已完成）
- [x] 修复 Electron hardenedRuntime（已完成）
- [ ] Electron 配置标记 deprecated（README 标注）
- [ ] v0.26.0 移除 Electron 相关文件
- [ ] Tauri Updater 配置
- [ ] Tauri 代码签名 CI

## 替代方案

保留双壳 —— 被否决，因为维护成本不可持续。
