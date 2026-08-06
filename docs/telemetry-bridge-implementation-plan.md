# MAREF 遥测桥梁 — 灰盒共研实施方案

> 基于 Momenta「灰盒共研」模式，利用 openclaw 真实部署数据作为 MAREF RSI 自演进燃料
> 版本: v0.1 | 日期: 2026-07-19

---

## 现状：数据链断裂全景

```
openclaw (Track A)                          public/maref (Track B)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                              ┌─────────────────┐
  101,166 条审计日志 （磁盘）                    │  进化引擎        │
  但：                                         │  engine.py       │
  ├─ HMAC 密钥未设置（链不可信）                  │  但：            │
  ├─ 不发送到任何地方                           │  ├─ FNR/FPR 全零 │
  └─ evolution/ 是 B 的过期副本                 │  ├─ 输入是 random │
                                              │  └─ never dry_run │
  ┌─────────────────┐                         │                   │
  │ OPC 调度循环      │                        │  ┌──────────────┐ │
  │ 但：             │                        │  │ RealMetrics  │ │
  │ ├─ 字节码已丢失   │                        │  │ quick_checks │ │
  │ └─ 不可运行      │                        │  │ = (0.0, 0.0) │ │
  └─────────────────┘                         │  └──────────────┘ │
                                              │                   │
  ┌─────────────────┐                         │  ┌──────────────┐ │
  │ observability/   │                        │  │ ObsPipeline  │ │
  │ + obs/           │                        │  │ endpoint  =  │ │
  │ 本地记录不发送    │                        │  │ telemetry.   │ │
  └─────────────────┘                         │  │ maref.org    │ │
                                              │  │ (可能 404)   │ │
                                              │  └──────────────┘ │
  ┌─────────────────┐                         └─────────────────────┘
  │ VAULT/           │
  │ RSI 实验记录 TSV │
  │ 但：只有 B 自己跑  │
  │ 的数据            │
  └─────────────────┘
```

**核心矛盾**: MAREF 设计了完整的 RSI 进化管道（SelfObserver → SelfDiagnostician → SelfArchitect → SelfExecutor → SelfOptimizer），但**只管道的每个输入端都没有真实部署数据**。进化引擎在"真空"中运转。

### 已确认的数据链断裂根因

代码追踪确认了 FNR/FPR 的虚假数据传播路径：

```
engine.py:316  _collect_detector_metrics(round_num)
  → config.metrics_mode="real"（默认）
    → RealMetricsCollector.collect_incremental()
      → _run_quick_checks()
        → return RealMetrics(fnr=0.0, fpr=0.0, ...) ← 硬编码零!
          ↓
engine.py:363  _run_meta_learning_step(round_num, fnr=0.0)
  → reward = 1.0 - (0.0 * 2.0) = 1.0
  → MetaLearner 永远收到正奖励 → 策略永不更新!
```

`RealMetricsCollector` 有完整的 `_run_all_checks()`（L60-94），它会跑 pytest 并计算真实 pass/fail → FNR，但 `collect_incremental()` 错误地调用了 `_run_quick_checks()`（L96-111），后者直接返回 `fnr=0.0, fpr=0.0`。

**修复只需一行**: 将 `collect_incremental()` 改为调用 `_run_all_checks()`。

---

## 灰盒共研数据契约

### 数据主权边界

| 数据类别 | 包含字段 | 归属 | 是否出域 |
|----------|---------|------|---------|
| **治理元数据** | 事件类型、状态转换、FNR/FPR、决策路径、熵值变化 | MAREF | ✅ 可上报 |
| **审计链头部** | id、timestamp、event_type、actor、action | MAREF | ✅ 可上报 |
| **审计链签名** | previous_hash、chain_hash、hmac_signature | MAREF | ✅ 可上报 |
| **性能指标** | 延迟、吞吐量、CircuitBreaker 状态 | MAREF | ✅ 可上报 |
| **业务 payload** | 文件路径、决策内容、数据分类 | 企业 | ❌ 保留本地 |
| **Agent 身份** | 具体 Agent 名称、内部 ID | 企业 | ❌ 保留本地 |
| **代码内容** | 被治理的代码片段、配置 | 企业 | ❌ 保留本地 |

### 脱敏规则

```
上报前自动执行:
  1. metadata.details → 摘除（字符串内容）
  2. metadata.data_classification → 摘除
  3. actor → hash(actor + deployment_secret) 单向脱敏
  4. 保留: timestamp, event_type, action, from_state, to_state, entropy, chain_hash
```

---

## 实施方案

### 阶段 0：修复 RSI 管道的虚假数据（public/maref）

**目标**: 先让进化引擎能吃到真实数据，再考虑数据来源。

#### 0.1 修复 RealMetricsCollector（`real_metrics.py`）

```python
# 当前: _run_quick_checks() → always (0.0, 0.0)
# 改为: 从本地审计日志计算真实 FNR/FPR

def _run_quick_checks(self) -> RealMetrics:
    # 从本地 governance_audit.jsonl 读取最近 N 条记录
    audit_path = Path("governance_audit.jsonl")
    if audit_path.exists():
        fnr, fpr = self._compute_fnr_fpr_from_audit(audit_path)
    else:
        fnr, fpr = 0.0, 0.0  # fallback
    ...

def _compute_fnr_fpr_from_audit(self, path: Path) -> tuple[float, float]:
    """从审计日志计算 FNR/FPR。
    
    FNR = 漏报 / (命中 + 漏报)
      = governance_decision=BLOCK但实际发生了违规 / 总违规
    FPR = 误报 / (误报 + 正确放行)
      = governance_decision=BLOCK但实际是合法操作 / 总放行
    """
    entries = self._read_recent_entries(path, window=1000)
    false_negatives = sum(1 for e in entries if self._is_false_negative(e))
    true_positives = sum(1 for e in entries if self._is_true_positive(e))
    false_positives = sum(1 for e in entries if self._is_false_positive(e))
    true_negatives = sum(1 for e in entries if self._is_true_negative(e))

    fnr = false_negatives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    fpr = false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else 0.0
    return fnr, fpr
```

#### 0.2 修复 MultiAgentEvolutionEngine（`multi_agent_engine.py`）

```python
# 当前: _simulate_detector_metrics() → fixed random
# 改为:

def _collect_detector_metrics(self, mode: str = "simulated") -> dict:
    if mode == "real":
        collector = RealMetricsCollector()
        metrics = collector.collect_incremental()
        return {"fnr": metrics.fnr, "fpr": metrics.fpr}
    # fallback to simulated
    return self._simulate_detector_metrics()
```

#### 0.3 修复 SelfObserver（`self_observer.py`）

```python
# 当前: observe_tests() → collect_only=True → 无 pass/fail
# 改为:

def observe_tests(self, collect_only: bool = False) -> TestStats:
    if not collect_only:
        result = subprocess.run(
            ["pytest", "tests/", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=120
        )
        # 从 stdout 解析: "3 passed, 1 failed"
        ...
```

#### 0.4 生成 OpenClaw 审计适配器（`evaluation/saeb/openclaw_adapter.py`）

```python
"""将 openclaw 治理审计日志转换为 SAEB 兼容指标。"""

class OpenClawAuditAdapter:
    def __init__(self, audit_path: Path):
        self._path = audit_path
    
    def to_saeb_metrics(self, window: int = 1000) -> SAEBMetrics:
        """读取 openclaw 审计日志，提取治理相关指标。"""
        entries = self._read_entries(window)
        return SAEBMetrics(
            fnr=self._compute_fnr(entries),
            fpr=self._compute_fpr(entries),
            state_transition_entropy=self._compute_entropy(entries),
            circuit_breaker_trip_rate=self._compute_cb_rate(entries),
            ...
        )
    
    @property
    def aggregate_report(self) -> dict:
        """返回聚合报告，供 evolution vault 记录。"""
```

#### 0.5 修复 HMAC 密钥缺失

从 `.maraf_hmac_key` 读取（开发）或 `MAREF_HMAC_SECRET_KEY` 环境变量（生产），传入 AuditLogger。

---

### 阶段 1：openclaw 遥测导出器

**目标**: 将 openclaw 的治理数据脱敏后导出，作为 MAREF 进化引擎的燃料。

#### 1.1 创建 `src/maref/opc/telemetry_exporter.py`

```python
"""
OPC 遥测导出器 — 将治理审计日志脱敏后上报。

灰盒模式：
- 只导出治理元数据（事件类型、状态转换、决策路径）
- 不导出业务 payload（文件路径、数据分类、具体内容）
- Actor 名称 HMAC 脱敏
"""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

class TelemetryExporter:
    """治理遥测导出器。"""
    
    def __init__(self, 
                 audit_path: Path,
                 deployment_id: str,
                 hmac_secret: str,
                 endpoint: str = "https://maref.cc/api/v1/telemetry"):
        self._audit_path = audit_path
        self._deployment_id = deployment_id
        self._hmac_key = hmac_secret.encode()
        self._endpoint = endpoint
    
    def _anonymize_entry(self, entry: AuditEntry) -> dict[str, Any]:
        """脱敏单条审计条目。"""
        return {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "event_type": entry.event_type,
            "actor": self._hash_actor(entry.actor),  # 脱敏
            "action": entry.action,
            # 不包含 details（可能含业务内容）
            "metadata": {
                k: v for k, v in entry.metadata.items()
                if k not in ("data_classification", "file_path")  # 摘除业务字段
            },
            "chain_hash": entry.chain_hash,
            "hmac_signature": entry.hmac_signature,
        }
    
    def _hash_actor(self, name: str) -> str:
        return hmac.new(self._hmac_key, name.encode(), hashlib.sha256).hexdigest()[:16]
    
    def export_batch(self, max_entries: int = 1000) -> list[dict]:
        """导出脱敏批次。"""
        entries = self._read_recent_audit(max_entries)
        return [self._anonymize_entry(e) for e in entries]
    
    def send_batch(self) -> dict:
        """发送批次到 maref.cc。"""
        batch = self.export_batch()
        # HTTP POST to endpoint
        # 指数退避重试，静默失败
        
    def _compute_report(self) -> dict:
        """生成聚合报告: FNR/FPR/熵值/吞吐量"""
        entries = self._read_recent_audit(5000)
        return {
            "fnr": self._compute_fnr(entries),
            "fpr": self._compute_fpr(entries),
            "avg_entropy": self._compute_avg_entropy(entries),
            "transition_throughput": self._compute_throughput(entries),
            "cb_trip_rate": self._compute_cb_rate(entries),
            "total_entries": len(entries),
            "window_hours": 24,
        }
```

#### 1.2 集成到 OPC 调度循环

在 `opc/evaluator.py`（或重建的 OPC 循环）的 EVALUATE 阶段后注入遥测导出：

```
SCAN → DISPATCH → EXECUTE → EVALUATE → TELEMETRY → AUDIT/ARCHIVE
                                         ↑
                               新增步骤: 脱敏 + 上报
```

#### 1.3 创建 CLI 命令

```bash
maref opc telemetry export     # 脱敏导出到 stdout
maref opc telemetry send       # 发送到 maref.cc
maref opc telemetry status     # 检查上次上报时间/条数
```

---

### 阶段 2：maref.cc 遥测接收器

**目标**: 接收多个部署实例的脱敏治理数据，聚合计算全局指标。

#### 2.1 API 端点设计

```
POST /api/v1/telemetry/batch
  Body: {
    deployment_id: string,        // 部署实例 ID
    telemetry_version: "1.0",
    batch_id: string,             // 批次 ID（防重放）
    entries: TelemetryEntry[],    // 脱敏条目
    aggregate: AggregateReport,   // 聚合报告
    hmac_signature: string,       // 批次 HMAC 签名
  }
  Response: {
    status: "accepted",
    batch_id: string,
    policies_updated: bool,
    latest_version: string,       // 最新 MAREF 版本
  }

GET /api/v1/telemetry/aggregate
  Response: {
    global_fnr: float,
    global_fpr: float,
    deployment_count: int,
    total_events: int,
    top_anomalies: AnomalySummary[],
  }

GET /api/v1/policies/latest
  Response: {
    version: string,
    safety_gate_defaults: {...},
    circuit_breaker_defaults: {...},
    trigram_weights: {...},
  }
```

#### 2.2 数据聚合器（`evolution/aggregator.py`）

```python
"""
跨部署遥测聚合器。

接收来自 N 个 openclaw 实例的脱敏治理数据，
计算全局 FNR/FPR/熵值趋势，驱动进化引擎。
"""

@dataclass
class GlobalMetrics:
    deployments: int
    total_events: int
    global_fnr: float
    global_fpr: float
    global_avg_entropy: float
    fnr_trend: Literal["improving", "stable", "degrading"]
    fpr_trend: Literal["improving", "stable", "degrading"]
    
class TelemetryAggregator:
    def ingest(self, batch: TelemetryBatch) -> None:
        """接收来自单个部署实例的批次。"""
        self._store_batch(batch)
        self._recompute_globals()
    
    def recompute_globals(self) -> GlobalMetrics:
        """重新计算全局指标。"""
        all_entries = self._query(window_days=7)
        return GlobalMetrics(
            deployments=self._count_active_deployments(),
            total_events=len(all_entries),
            global_fnr=self._weighted_fnr(all_entries),
            global_fpr=self._weighted_fpr(all_entries),
            ...
        )
    
    def detect_global_anomalies(self) -> list[AnomalyReport]:
        """跨部署异常检测。"""
        # 如果多个部署同时出现某类状态转换异常 → 可能是 MAREF 内核缺陷
        # 如果单个部署出现离群值 → 可能是该部署的配置问题
```

#### 2.3 进化引擎燃料注入

```python
# 在 evolution/engine.py 中新增数据源

class RecursiveEvolutionEngine:
    def __init__(self, telemetry_source: TelemetrySource | None = None):
        self._telemetry = telemetry_source  # 可选: 真实遥测数据源
    
    def run_round(self, round_config: RoundConfig) -> RoundResult:
        if self._telemetry:
            metrics = self._telemetry.fetch_global_metrics()
            # 使用真实数据驱动进化
            self._meta_learner.step(
                reward=1.0 - (metrics.global_fnr * 2.0 + metrics.global_fpr)
            )
        else:
            # 退化到 simulated 模式
            metrics = self._simulate_metrics()
```

---

### 阶段 3：版本更新管道

#### 3.1 maref.cc 发布注册

```
GET /api/v1/releases/latest
  Response: {
    version: "0.37.0",
    published_at: "2026-07-19",
    changelog_url: "/docs/changelog/0.37.0",
    download_url: "https://github.com/maref-org/maref/releases/tag/v0.37.0",
    migration_guide: "/docs/migration/0.36-to-0.37",
    critical_updates: [
      {"module": "governance/audit.py", "type": "security", "severity": "high"},
    ]
  }

GET /api/v1/policies/diff?from=0.35.0&to=0.37.0
  Response: {
    safety_gate: {added: [...], removed: [...], changed: [...]},
    circuit_breaker: {threshold_changed: {...}},
    trigram_weights: {changed: {...}},
  }
```

#### 3.2 openclaw 更新检查

```bash
maref update check              # 检查最新版本
maref update policy --diff      # 检查策略差异
maref update apply --policy     # 应用策略更新（需人类确认）
```

#### 3.3 策略同步集成到 OPC

```python
# opc/ 启动时自动执行:
# 1. maref update check → 如果新版本可用，记录到工作区
# 2. maref update policy --diff → 如果需要策略更新，触发 HITL
# 3. 如果策略更新获得审批，自动应用
```

---

### 阶段 4：进化飞轮闭环验证

#### 4.1 闭环指标

```
部署 → 治理数据 → 脱敏上报 → 全局聚合 → 进化引擎 → 策略迭代 → 部署
 └──────────────────── 闭环周期 ────────────────────────────┘

成功标准:
  • 闭环周期 < 7 天（从数据产生到策略生效）
  • 全局 FNR 每周期下降 ≥ 5%
  • 全局 FPR 每周期下降 ≥ 3%
  • 误报率（人为纠正）每周期下降 ≥ 10%
```

#### 4.2 验证方法

```bash
# 在 public/maref 中
pytest tests/evolution/ -v --cov=src/maref/evolution

# 模拟多部署场景
python -m maref.evolution.test_telemetry_ingest

# 端到端: 生成模拟审计数据 → 脱敏 → 聚合 → 进化 → 策略输出
python -m maref.evolution.e2e_test --simulate-deployments=3 --rounds=10
```

---

## 文件清单

### public/maref 新增/修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/maref/evaluation/saeb/openclaw_adapter.py` | 新增 | 审计日志 → SAEB 指标适配器 |
| `src/maref/evolution/telemetry_source.py` | 新增 | 遥测数据源接口 + HTTP 客户端 |
| `src/maref/evolution/aggregator.py` | 新增 | 跨部署遥测聚合器 |
| `src/maref/recursive/real_metrics.py` | 修改 | 修复 `_run_quick_checks()` 全零问题 |
| `src/maref/recursive/multi_agent_engine.py` | 修改 | 接入 `RealMetricsCollector` |
| `src/maref/recursive/self_observer.py` | 修改 | `observe_tests()` 支持真实执行 |
| `src/maref/governance/audit.py` | 修改 | 默认从 `.maraf_hmac_key` 读取密钥 |

### openclaw 新增/修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/maref/opc/telemetry_exporter.py` | 新增 | 审计日志脱敏导出器 |
| `src/maref/opc/telemetry_config.py` | 新增 | 遥测配置（endpoint/密钥/频率） |
| `src/maref_lite/commands/opc_telemetry.py` | 新增 | CLI 命令 |
| `src/maref/opc/loop.py` | 修改 | 集成 TELEMETRY 步骤 |

### maref.cc 新增

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/telemetry/batch` | POST | 接收脱敏遥测批次 |
| `/api/v1/telemetry/aggregate` | GET | 查询全局聚合指标 |
| `/api/v1/policies/latest` | GET | 获取最新治理策略 |
| `/api/v1/policies/diff` | GET | 策略版本差异 |
| `/api/v1/releases/latest` | GET | 最新版本信息 |

---

## 实施路线图

```
Phase 0: 修复 RSI 数据链  (1-2 周)
  ├─ 0.1 RealMetricsCollector 修复
  ├─ 0.2 MultiAgentEvolutionEngine 真实数据接入
  ├─ 0.3 SelfObserver 真实测试执行
  ├─ 0.4 OpenClawAuditAdapter
  └─ 0.5 HMAC 密钥配置修复

Phase 1: openclaw 遥测导出器  (1-2 周)
  ├─ 1.1 TelemetryExporter 实现
  ├─ 1.2 OPC 循环集成
  └─ 1.3 CLI 命令

Phase 2: maref.cc 遥测接收器  (1-2 周)
  ├─ 2.1 API 端点
  ├─ 2.2 TelemetryAggregator
  └─ 2.3 进化引擎连接

Phase 3: 版本更新管道  (1 周)
  ├─ 3.1 发布注册 API
  ├─ 3.2 update check CLI
  └─ 3.3 OPC 策略同步

Phase 4: 闭环验证  (持续)
  ├─ 4.1 闭环指标定义
  └─ 4.2 e2e 测试
```

---

## 附录：关键数据流示例

### 脱敏前后对比

```json
// 原始审计条目 (openclaw 本地)
{
  "id": "audit_001234",
  "timestamp": 1784182617.255,
  "event_type": "governance_decision",
  "actor": "claude_code",
  "action": "BLOCK",
  "details": "Attempted write to /etc/passwd — high risk file",
  "metadata": {
    "file_path": "/etc/passwd",
    "risk_score": 0.95,
    "data_classification": "SYSTEM_CRITICAL",
    "from_state": "EXECUTING",
    "to_state": "PAUSED"
  },
  "chain_hash": "a1b2c3..."
}

// 脱敏后 (发送到 maref.cc)
{
  "id": "audit_001234",
  "timestamp": 1784182617.255,
  "event_type": "governance_decision",
  "actor": "a1b2c3d4e5f6a7b8",        // HMAC 脱敏
  "action": "BLOCK",
  // 无 details — 摘除
  "metadata": {
    // 无 file_path — 摘除
    // 无 data_classification — 摘除
    "risk_score": 0.95,
    "from_state": "EXECUTING",
    "to_state": "PAUSED"
  },
  "chain_hash": "a1b2c3..."
}
```

### FNR/FPR 计算示例

```
FNR = BLOCK 事件中本应拦截但未拦截的比例
     = 漏报数 / (漏报数 + 正确拦截数)
     = count(action=BLOCK ∧ is_violation) / count(all_violations)

FPR = BLOCK 事件中误拦截的比例  
     = 误报数 / (误报数 + 正确放行数)
     = count(action=BLOCK ∧ is_innocent) / count(all_decisions)

在审计日志中:
  is_violation = 后续有 rollback/incident 记录
  is_innocent  = 后续有人工 override 或 recovery 记录

从实时数据脱敏到进化飞轮仅需 1 个入口点(telemetry_exporter.py)
```
