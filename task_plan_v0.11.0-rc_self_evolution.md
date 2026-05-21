# MAREF v0.11.0-rc: 激进自主递归演进 10 轮实施方案

**计划日期**: 2026-05-08  
**起始版本**: v0.9.0-rc (R40)  
**目标版本**: v0.11.0-rc (R60)

---

## 版本路线

```
v0.9.0-rc (R40) ──→ Step 0: commit R41-R47 → v0.10.0-rc-dev
                                              ──→ R51-R60 → v0.11.0-rc
```

---

## Step 0: 技术债清理

- [x] Commit R41-R47 (HybridDecomposer, AgentHandoff, AgentMarketplace, SafetyGateV2 ext, OrchestrationPerf + 7 tests)
- [ ] Bump pyproject.toml: v0.9.0-rc → v0.10.0-rc-dev
- [ ] Tag: v0.10.0-rc-dev

---

## 十轮演进

### R51 | 基线校准 + SelfHealer 执行层补强
**目标**: 建立演化前基线快照，SelfHealer 6 个策略从模拟→真实执行

| 文件 | 方法/位置 | 变更 |
|------|----------|------|
| `self_healer.py:91` | `heal()` | `result="simulated_recovery"` → 按策略分发真实 subprocess |
| `self_healer.py:119` | `heal_cycle()` | 强制 NORMAL → 重新调用 SelfDiagnostician.diagnose() |
| `self_healer.py:43` | `to_unified()` | timestamp=0.0 → time.time() |
| 新增 | `_execute_strategy()` | 策略→真实操作映射 |

- [ ] 6 个策略全部真实化
- [ ] 基线采集：SelfDiagnostician 全量扫描
- [ ] 测试: `pytest tests/recursive/test_r3_healing.py -v`
- [ ] Tag: v0.11.0-rc-r51

---

### R52 | SelfOptimizer 执行层补强
**目标**: SelfOptimizer 从硬编码假数据→真实 pytest+coverage 基准

| 文件 | 方法/位置 | 变更 |
|------|----------|------|
| `self_optimizer.py:72-76` | `run_experiment()` | 硬编码 before → 真实 _run_benchmark() |
| `self_optimizer.py:78-83` | `run_experiment()` | 模拟 after → 真实 _run_benchmark() |
| `self_optimizer.py:88` | `run_experiment()` | max(gain,0) → 允许负增益 |
| 新增 | `_run_benchmark()` | 封装 pytest + coverage subprocess |

- [ ] _run_benchmark() 实现
- [ ] 测试补强：fixture 使用 tempfile + 真实项目
- [ ] 测试: `pytest tests/recursive/test_r4_optimization.py -v`
- [ ] Tag: v0.11.0-rc-r52

---

### R53 | 第一波激进参数演进（治理层）
**目标**: 在 PolicySandbox 保护下激进搜索治理参数空间

| 参数 | 当前 → 激进 |
|------|------------|
| adoption_gain_threshold | 0.05 → 0.03 |
| sandbox_auto_revert_minutes | 30 → 60 |
| max_recursion_depth | 3 → 4 |
| meta_cb_trip_threshold | 3 → 4 |
| circuit_breaker_cooldown | 30s → 15s |
| oscillation_max_rate | 10.0 → 15.0 |
| SATURATION_THRESHOLD | 0.005 → 0.003 |
| SATURATION_WINDOW | 3 → 5 |

- [ ] 8 个参数开放搜索
- [ ] PolicySandbox A/B 验证
- [ ] 测试: 治理层 + meta + policy_sandbox
- [ ] Tag: v0.11.0-rc-r53

---

### R54 | 第二波激进参数演进（学习层）
**目标**: 激进优化 MetaLearner 超参数

| 参数 | 当前 → 激进 |
|------|------------|
| learning_rate | 0.01 → 0.02 |
| min_learning_rate | 0.001 → 0.0005 |
| discount_factor | 0.95 → 0.90 |
| buffer_size | 1000 → 2000 |
| min_samples_for_optimize | 50 → 30 |
| batch_size | 100 → 200 |
| HALT_penalty | -5.0 → -8.0 |

- [ ] 7 个超参激进调整
- [ ] 稳定性验证: std_dev < 0.5 over 20 episodes
- [ ] 测试: test_meta_learning.py + test_meta_learning_m5.py
- [ ] Tag: v0.11.0-rc-r54

---

### R55 | 参数演进收敛 + 全量回归
**目标**: 锁定参数，全量验证无回归

- [ ] PolicySandbox 回滚未通过测试的参数
- [ ] 对比 R51 基线 vs R55 终态
- [ ] 全量 pytest 2341+
- [ ] coverage --fail-under=80
- [ ] 自动回退任何导致测试失败或覆盖率下降 >2% 的参数
- [ ] Tag: v0.11.0-rc-r55

---

### R56 | SelfArchitect + ContinuousOptimizer 补强
**目标**: AST 级依赖分析 + ContinuousOptimizer 真实化

| 文件 | 变更 |
|------|------|
| `self_architect.py` | 新增 _analyze_ast_dependencies(), _compute_coupling_metrics() |
| `self_architect.py:55` | proposed_arch 占位 → 数据驱动的 proposal |
| `continuous_optimizer.py:111` | sandbox_test() → 调用 SelfOptimizer._run_benchmark() |
| `continuous_optimizer.py:193` | 假覆盖率列表 → coverage report -m 解析 |
| `continuous_optimizer.py:192` | 硬编码 unused_imports → ast.parse() 真实分析 |

- [ ] AST 依赖分析
- [ ] 真实覆盖率采集
- [ ] 真实未使用导入检测
- [ ] Tag: v0.11.0-rc-r56

---

### R57 | EvolutionDSL + ResilienceV2 真实化
**目标**: simulate()→真实 benchmark；降级计划→真实执行

| 文件 | 变更 |
|------|------|
| `evolution_dsl.py:163` | 硬编码 stability → 真实 benchmark |
| `evolution_dsl.py` SafetyGate | 扩展检查：test_pass_rate, coverage_drop, perf_regression |
| `resilience_v2.py` | 3 个降级策略 → 真实 CB.open(), Collector.stop(), Coordinator.isolate() |

- [ ] simulate() 真实 benchmark
- [ ] SafetyGate 扩展 3 项检查
- [ ] 降级策略真实执行
- [ ] Tag: v0.11.0-rc-r57

---

### R58 | 受限代码演进（安全沙箱内首次）
**目标**: SelfExecutor 在 git 分支上首次真实代码变更

**前置条件** (all must pass):
- [ ] 在专用 git 分支 feature/self-evolution-r58
- [ ] R51-R57 全量测试通过
- [ ] SelfExecutor.dry_run() 通过
- [ ] SafetyGateV2 确认核心 5 组件受保护

**允许范围**: 添加测试、删除未使用导入、修复简单 import 错误  
**禁止范围**: 修改 5 核心组件、eval/exec/subprocess

- [ ] SelfArchitect → CodeGenerator → ASTSandbox → SafetyGateV2 → AtomicDeployer pipeline
- [ ] 全量测试通过后保留，失败自动回滚
- [ ] Tag: v0.11.0-rc-r58

---

### R59 | 全系统混沌 + 弹性压力验证
**目标**: 验证演化后系统的极限承受力

| 混沌注入 | 持续时间 | 期望响应 |
|----------|----------|----------|
| CB_OSCILLATION | 60s | OscillationFixLoop 检测 → MetaCB 不触发 |
| HALT_STORM | 30s | CB OPEN → 降级 → Auto-Revert |
| AGENT_CRASH (3x) | — | SelfHealer 真实恢复 |
| KG_CORRUPTION | 1次 | KGProbe → 重建 |
| RAPID_PARAMETER_CHURN | 20/60s | PolicySandbox → 自动回退 |

- [ ] ResilienceEvaluatorV2 总分 > 75
- [ ] SelfHealer 真实成功率 > 80%
- [ ] Tag: v0.11.0-rc-r59

---

### R60 | 收敛验证 + v0.11.0-rc 发布
**目标**: 最终验证，锁定参数，打版本标签

- [ ] 全量 pytest → 0 失败
- [ ] coverage > 95%
- [ ] ResilienceEvaluatorV2 终态评分
- [ ] 导出最终参数集: policy_versions/v0.11.0-rc.json
- [ ] 更新 pyproject.toml: version = "0.11.0-rc"
- [ ] 更新 CHANGELOG.md
- [ ] git tag: v0.11.0-rc
- [ ] 合并 feature/self-evolution-r58 → main (if successful)

---

## 测试增长预期

| 轮次 | 测试数 | 增量 |
|------|--------|------|
| R51 | 2353 | +12 |
| R52 | 2363 | +10 |
| R53 | 2363 | — |
| R54 | 2363 | — |
| R55 | 2365 | +2 |
| R56 | 2375 | +10 |
| R57 | 2385 | +10 |
| R58 | 2400 | +15 |
| R59 | 2400 | — |
| R60 | 2400+ | final |
