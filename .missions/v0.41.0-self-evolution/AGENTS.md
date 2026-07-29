# Agent Operating Manual: MAREF v0.41.0 Self-Evolution GA

> **上位法**: [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md)。冲突时宪法优先。
> **本 mission 范围**: v0.41.0 — 递归自演进 GA。不修改全局 AGENTS.md。

## 概要

- **名称**: MAREF Self-Evolution GA
- **版本**: v0.41.0-dev
- **定位**: 递归自演进引擎接入真实系统指标，替换模拟数据，实现生产级闭环
- **技术栈**: Python 3.10+ / SQLite / asyncio / subprocess

## 关键缺口

Athena 自主递归演进闭环分析 (2026-06-07) 识别:

| # | 缺口 | 严重度 | 方案 |
|---|------|--------|------|
| 1 | RealMetricsCollector 未接入演进引擎 | 🔴 高 | SelfObserver → RecursiveEvolutionEngine |
| 2 | EvolutionVault 不完整 | 🔴 高 | 跨轮次持久化存储 |
| 3 | 每日演进入口不完整 | 🟡 中 | 升级 run_daily.sh 覆盖完整闭环 |

## 里程碑

| ID | 名称 | 交付 |
|----|------|------|
| e1 | RealMetricsCollector | SelfObserver.snapshot() → RecursiveEvolutionEngine.run_once() |
| e2 | EvolutionVault | SQLite 持久化 + 跨轮次趋势追踪 |
| e3 | DailyEvolutionLoop | 完整 8 阶段闭环自动化脚本 |
| e4 | 7 天验证 | 连续 7 天自主演进 + 稳定性断言 |

## 关键文件

| 组件 | 路径 |
|------|------|
| 演进引擎 | `src/maref/evolution/engine.py` |
| 自观察器 | `src/maref/recursive/self_observer.py` |
| 自诊断器 | `src/maref/recursive/self_diagnostician.py` |
| 自执行器 | `src/maref/recursive/self_executor.py` |
| 每日循环 | `src/maref/evolution/daily_loop.py` |
| 演进 Vault | `src/maref/evolution/evolution_vault.py` (新建) |
| 演进适配器 | `src/maref/evolution/tla_adapter.py` |
