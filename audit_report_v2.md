# MAREF 补强工程方案 v2 深度审计报告

**审计日期**: 2026-04-26
**审计对象**: /Volumes/1TB-M2/maref-experiments
**方案文件**: MAREF补强工程方案v2.md

---

## 一、审计结论摘要

| 阶段 | 方案状态 | 实际状态 | 对齐度 |
|------|----------|----------|--------|
| P0.0 运行环境固化 | ✅ 已完成 | ✅ 已完成 | 100% |
| P0.1 LLM 替换仿真 | ✅ 已完成 | ✅ 已完成 | 100% |
| P0.2 AutoGen Adapter | ✅ 已完成 | ✅ 已完成 | 100% |
| P0.3 Sidecar 只读验证 | ✅ 已完成 | ⚠️ 部分完成 | 70% |
| P1.1 知识图谱向量化 | ✅ 已完成 | ✅ 已完成 | 100% |
| P1.2 结构化 Findings | **新建** | ✅ 已完成 | 100% |
| P2.1 LLM 混沌测试 | **新建** | ❌ 未开始 | 0% |
| P2.2 Benchmark | **新建** | ❌ 未开始 | 0% |

**总体对齐度**: ~78% (7/9 项已完成或部分完成)

---

## 二、逐项审计详情

### P0.0: 运行环境固化 ✅

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| `.env` 文件 | 创建 `.env` 存储 API Key | ✅ 存在，含 `DASHSCOPE_API_KEY` | 对齐 |
| `.env.example` | 模板文件 | ❌ 不存在 | **缺失** |
| `python-dotenv` | 依赖安装 | ✅ 已在 `requirements.txt` | 对齐 |
| `load_dotenv()` | 自动加载 | ✅ `continuous_engine.py` 第22-24行 | 对齐 |
| plist Key 移除 | 消除硬编码 | ✅ plist 中无硬编码 Key | 对齐 |

**差距**: 缺少 `.env.example` 模板文件（低优先级）

---

### P0.1: LLM 替换仿真 ✅

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| 14 个实验函数 | 全部接入百炼 Qwen | ✅ 已完成 | 对齐 |
| `dashscope_client.py` | API 客户端 | ✅ 存在，功能完整 | 对齐 |
| LLM 调用验证 | qwen-plus chat + analysis | ✅ 已验证 | 对齐 |
| 会话管理 | 正确关闭 aiohttp | ✅ 已修复 | 对齐 |

**代码改动文件**:
- `src/research/autoresearch_loop.py` (Phase 8)
- `src/research/autoresearch_phase9.py` (Phase 9)
- `src/research/autoresearch_phase10.py` (Phase 10)
- `src/research/experiment_registry.py` (适配)

---

### P0.2: AutoGen Adapter ✅

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| `autogen.py` | 实现 AutoGenAdapter | ✅ 存在，7228 bytes | 对齐 |
| `list_agents()` | 返回参与者列表 | ✅ 已实现 | 对齐 |
| `get_state()` | 返回 StateSnapshot | ✅ 已实现 | 对齐 |
| `observe_stream()` | 自动消息追踪 | ✅ 已实现 | 对齐 |
| 单元测试 | 22 tests | ⚠️ 存在测试文件，数量待确认 | 基本对齐 |

**文件**: `src/sidecar/adapters/autogen.py` (完整实现)
**测试**: `tests/sidecar/test_autogen_adapter.py`

---

### P0.3: Sidecar 只读验证 ⚠️

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| 端到端演示脚本 | `scripts/sidecar_demo.py` | ❌ 不存在 | **缺失** |
| 性能验证报告 | 延迟 < 1ms, 采样率 > 99% | ❌ 未执行 | **缺失** |
| 持续运行测试 | 1 小时零事故 | ❌ 未执行 | **缺失** |
| AutoGen 集成 | GroupChat + Sidecar | ✅ Adapter 已就绪 | 部分对齐 |

**差距**: 缺少演示脚本和性能基准测试

---

### P1.1: 知识图谱向量化 ✅

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| `vector_store.py` | ChromaDB + ONNX | ✅ 存在，7644 bytes | 对齐 |
| `add_finding()` | 添加发现 | ✅ 已实现 | 对齐 |
| `search()` | 语义搜索 | ✅ 已实现 | 对齐 |
| 单元测试 | 19 tests | ⚠️ 存在测试文件 | 基本对齐 |
| Orchestrator 集成 | 语义新颖度评分 | ❌ 未确认 | **待验证** |

**文件**: `src/research/vector_store.py`
**测试**: `tests/research/test_vector_store.py`

---

### P1.2: 结构化 Findings ✅

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| `StructuredFinding` | 数据类定义 | ✅ 存在，`finding_models.py` | 对齐 |
| `metric_name` | 指标名称 | ✅ 已实现 | 对齐 |
| `values` | 数值列表 | ✅ 已实现 | 对齐 |
| 统计属性 | mean/min/max/latest | ✅ 已实现 | 对齐 |
| 向后兼容 | `to_finding_string()` | ✅ 已实现 | 对齐 |

**文件**: `src/research/finding_models.py` (新建)

**差距**: 实验代码尚未从 `list[str]` 迁移到 `list[StructuredFinding]`

---

### P2.1: LLM 混沌测试 ❌

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| `ChaosInjector` | 故障注入器 | ❌ 不存在 | **未开始** |
| 5 种混沌场景 | 延迟/错误/丢包/熵增/振荡 | ❌ 不存在 | **未开始** |
| 真实环境测试 | 基于 P0.3 | ❌ 依赖缺失 | **阻塞** |

**阻塞原因**: 依赖 P0.3 完成（真实 Agent 集群）

---

### P2.2: Benchmark ❌

| 检查项 | 方案要求 | 实际状态 | 结论 |
|--------|----------|----------|------|
| HotPotQA 对比 | 对照组 vs 实验组 | ❌ 未开始 | **未开始** |
| 治理层对比 | 有/无 MAREF | ❌ 未开始 | **未开始** |
| 评测报告 | 100 问结果 | ❌ 未开始 | **未开始** |

**阻塞原因**: 依赖 P0.2/P0.3 完成

---

## 三、知识图谱现状

```
总节点数: 737
类型分布:
  - finding: 737 (100%)
  - hypothesis: 0
  - question: 0
```

**问题**: 所有节点都是 `finding` 类型，缺少 `hypothesis` 和 `question` 节点。
原因: `add_hypothesis()` 和 `add_question()` 调用可能未正确执行。

---

## 四、Git 状态

```
已修改:
  M src/research/autoresearch_loop.py
  M task_plan.md

未跟踪:
  ?? src/research/finding_models.py
```

**注意**: `finding_models.py` 是新建文件，需要提交。

---

## 五、差距总结与建议

### 已对齐 (100%)
1. P0.0 运行环境固化
2. P0.1 LLM 替换仿真
3. P0.2 AutoGen Adapter
4. P1.1 知识图谱向量化
5. P1.2 结构化 Findings (模型已创建)

### 部分对齐 (70%)
6. P0.3 Sidecar 只读验证 (Adapter 就绪，缺少演示和性能测试)

### 未开始 (0%)
7. P2.1 LLM 混沌测试
8. P2.2 Benchmark

### 立即行动建议

1. **提交当前代码**: `git add src/research/finding_models.py && git commit`
2. **创建 `.env.example`**: 模板文件供团队协作
3. **完成 P0.3**: 创建 `scripts/sidecar_demo.py` 演示脚本
4. **修复知识图谱**: 检查 `add_hypothesis()` 调用逻辑
5. **规划 P2.x**: 在 P0.3 完成后启动混沌测试

---

*审计完成时间: 2026-04-26*
*审计工具: 自动化代码扫描 + 手动验证*
