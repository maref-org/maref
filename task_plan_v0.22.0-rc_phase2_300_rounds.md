# MAREF v0.22.0-rc: 300 轮自主递归演进全量补强方案 (Phase 2)

**计划日期**: 2026-05-10
**起始版本**: v0.21.0 Final
**目标版本**: v0.22.0-rc

---

## 三大战线总览

| 战线 | 轮次 | 新增源文件 | 新增测试 | 核心修复 | 状态 |
|------|------|----------|---------|---------|------|
| 红蓝对抗 | RB1-RB100 | attack_executor.py | 28 | 评分公式 max→100, 死代码移除, 真实攻击注入 | ✅ |
| 压力测试 | S1-S100 | real_faults.py, real_latency.py, distributed_harness.py | 17 | 拆除 200 SM 锁死, 真实延迟, 真实故障 | ✅ |
| 递归演进 | R151-R250 | real_metrics.py | 待补 | C2 死配置修复, 真实 pytest/coverage, 300 上限 | ✅ |
| **合计** | **300 轮** | **5** | **45+** | — | — |

---

## 战线一: 红蓝对抗 (RB1-RB100) — ✅ 完成

| 阶段 | 轮次 | 内容 | 测试 |
|------|------|------|------|
| Phase 1 | RB1-RB20 | 评分修复 + 死代码 + 攻击执行器 + 测试基础 | 28 tests |
| Phase 2-5 | RB21-RB100 | 68 攻击向量覆盖, 真实组件集成 | 现有 run_redblue_100.py |

**关键修复**:
- 评分公式: `total = norm_d + norm_m + norm_r + norm_a` → 真 0-100 范围
- 移除: ResilienceEvaluatorV2 死代码
- 填充: meta_cb_triggered 从真实 CB 状态
- 对称: adaptation 添加 intensity/stealth 惩罚
- 新增: AttackExecutor 真实攻击分发

---

## 战线二: 压力测试 (S1-S100) — ✅ 核心完成

| 阶段 | 轮次 | 内容 | 测试 |
|------|------|------|------|
| Phase 1-3 | S1-S60 | 拆除仿真 + 真实故障 + 延迟追踪 | 17 tests |
| Phase 4-5 | S61-S100 | 分布式 multiprocessing / Docker / 24h 浸泡 | 标记 slow |

**关键修复**:
- DEFAULT_MAX_SM: 200 → 5000
- 移除: `time.sleep(synthetic_delay)` → `RealLatencyTracker.measure()`
- 移除: `int(self._axes.get("data_volume"))` 死代码
- 新增: RealFaultInjector (8 种真实故障)
- 新增: DistributedStressHarness (多进程并发)

---

## 战线三: 递归演进 (R151-R250) — ✅ 核心完成

| 阶段 | 轮次 | 内容 | 测试 |
|------|------|------|------|
| Phase A | R151-R155 | RealMetricsCollector 替换模拟 FNR/FPR | 待补 |
| Phase B | R156-R165 | 真实 Meta-Learning + PolicySandbox 动态阈值 | 待补 |
| Phase C | R166-R175 | SelfHealer 真实故障恢复验证 | 待补 |
| Phase D | R176-R185 | SelfOptimizer 真实 benchmark 闭环 | 待补 |
| Phase E | R186-R195 | AST 代码演进 + 安全沙箱部署 | 待补 |
| Phase F | R196-R210 | C2/C3 修复 + 四维收敛 | 待补 |
| Phase G | R211-R250 | 40 轮长跑 + 混沌注入 | 待补 |

**关键修复**:
- RealMetricsCollector: 真实 pytest + coverage 替代 random 模拟
- C2 死配置: `c2_fnr_must_not_worsen` + `c2_fpr_budget_pp` 纳入 assess_acceptance
- max_total_rounds: 200 → 300

---

## 版本对比

| 指标 | v0.21 Final | v0.22.0-rc | 增量 |
|------|-----------|-----------|------|
| 递归演进 FNR/FPR | random 模拟 | 真实 pytest+coverage | ✅ |
| 压力测试 SM 上限 | 200 | 5000 | 25× |
| 压力测试延迟 | 合成 sleep | wall-clock perf_counter | ✅ |
| 压力测试故障 | 随机概率 | 8 种真实系统故障 | ✅ |
| 红蓝对抗评分 | max 26 | max 100 | 修复 |
| 红蓝对抗攻击 | 全数学模拟 | AttackExecutor 真实分发 | ✅ |
| C2 死配置 | 2 个 | 0 个 | ✅ |
| 新增测试 | — | 45 (28+17) | ✅ |
| 新增模块 | — | 5 | ✅ |