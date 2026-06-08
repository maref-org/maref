# MAREF ROI 治理能力补强：全量实施方案

**版本**: v1.0  
**日期**: 2026-05-31  
**状态**: Draft  

---

## 一、架构总览

### 1.1 核心转变

```
旧范式: Cost Control（花得少 = 好）
        ↓
新范式: Value Optimization（花得值 = 好）
        roi = value_delivered / total_cost
        where value_delivered = output_quality × business_weight
```

### 1.2 新增模块全景

```
┌──────────────────────────────────────────────────────────────────┐
│                        六层治理 (现有)                            │
│  天极 → 人极 → 地极 → 经卦 → 别卦 → 爻变                       │
└──────────────────────────────────────────────────────────────────┘
                              │ ROI feedback at every layer
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ROI Governance Layer (新增)                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  ValueMeter  │  │ROICalculator │  │   AITheaterDetector   │  │
│  │  (value/task) │  │  (roi/agent) │  │  (behavior anomaly)   │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │                 │                       │              │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌───────────┴───────────┐  │
│  │StreamingROI  │  │ReworkTracker │  │ TokenEconomyMonitor   │  │
│  │Gate (实时)   │  │(返工成本)    │  │ (组织级分布)          │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │                 │                       │              │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌───────────┴───────────┐  │
│  │ROIPortfolio  │  │ROIForecast   │  │CollaborationROI      │  │
│  │Optimizer     │  │(预测+学习)   │  │(多Agent协作价值)     │  │
│  └──────────────┘  └──────────────┘  └───────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
             现有模块改造 (CostTracker / Budget / CreditRating / 
             Dispatcher / CapabilityContract / FSM / Trigram / Phase)
```

### 1.3 数据流

```
Task Entry
  │
  ▼
[ROIForecast] ── predicts ROI ──┐
  │                             │
  ▼                             ▼
[ROIPortfolioOptimizer] ── rank by predicted_roi ──► Dispatch
  │                                                    │
  ├─ High ROI → premium model + best agent             │
  ├─ Medium ROI → standard model                       │
  └─ Low ROI → cheap model / skip                     │
                                                       ▼
                                              [StreamingROIGate]
                                               mid-execution check
                                                       │
                                              ┌────────┤
                                              ▼        ▼
                                         continue   re-evaluate
                                                       │
                                                       ▼
                                              [ValueMeter]
                                               record value_delivered
                                                       │
                                                       ▼
                                              [ROICalculator]
                                               roi = value / cost
                                                       │
                                              ┌────────┼────────┐
                                              ▼        ▼        ▼
                                         [ReworkTracker]  [AITheaterDetector]
                                         adjust roi for    flag gaming
                                         rework cost
                                              │
                                              ▼
                                         [AgentCreditRating]
                                         ECONOMIC_EFFICIENCY dimension
                                              │
                                              ▼
                                         [TrigramsGovernance]
                                         ROI-based trust adaptation
                                              │
                                              ▼
                                         [ROIForecast]
                                         learn → improve next prediction
```

---

## 二、分阶段实施计划

### Phase 0：Value Foundation（价值度量基础）

**目标**: 让 MAREF 能度量 value，从而可算 ROI。

**涉及文件**: 新增 + 现有改造

#### 0A — ValueMeter（新增 `src/maref/recursive/value_meter.py`）

对称于 GasMeter。每种操作类型不仅消耗 gas，也交付价值。

```python
@dataclass
class OperationValue:
    operation_type: str
    base_value: float = 0.0        # 基础价值
    value_per_quality_delta: float = 0.0  # 每质量分价值增量
    max_value: float = 1.0         # 单次操作最大价值

class ValueMeter:
    """度量每次操作交付的价值，对称于 GasMeter。"""
    
    def meter(self, operation_type, quality_score=0.0, output_size=0) -> float
    def estimate(self, operation_type, quality_score=0.0) -> float
    def total_value(self) -> float
    def records(self) -> list[ValueRecord]

@dataclass  
class ValueRecord:
    operation_type: str
    value_delivered: float
    quality_score: float
    output_size: int = 0
    timestamp: float
    task_id: str = ""
    agent_id: str = ""
```

#### 0B — BenefitProfile（改造 `capability_contracts.py`）

对称于现有 CostProfile，给每个能力一个 "预计产出价值"。

```python
@dataclass
class BenefitProfile:
    expected_output_value: float = 0.0      # 预计价值
    value_metric: str = "quality_score"      # 价值度量方式
    quality_threshold: float = 0.6           # 最低质量阈值
    business_weight: float = 1.0             # 业务权重因子
    degradation_value: float = 0.0           # 降级模式下的价值
    
    def estimate(self, quality_score=0.0) -> float:
        if quality_score < self.quality_threshold:
            return 0.0
        return self.expected_output_value * quality_score * self.business_weight

# CapabilityContract 增加:
#   benefit_profile: BenefitProfile | None = None
```

#### 0C — ValueRecord 集成到 CostTracker（改造 `cost_tracker.py`）

`CostRecord` 增加值字段，让 cost_tracker 能查 ROI。

```python
@dataclass
class CostRecord:
    # ... 现有字段 ...
    value_delivered: float = 0.0     # 新增
    quality_score: float = 0.0       # 新增

class CostTracker:
    # 新增方法:
    def track_with_value(self, operation, cost, agent_id, task_id, 
                          value=0.0, quality=0.0) -> None
    def agent_roi(self, agent_id, window_hours=None) -> float
    def task_roi(self, task_id) -> float
```

#### 0D — ROI Calculator（新增 `src/maref/recursive/roi_calculator.py`）

核心 ROI 计算模块，多维度聚合。

```python
@dataclass
class ROIResult:
    agent_id: str
    total_value: float
    total_cost: float
    roi_ratio: float              # value / cost
    task_count: int
    window_hours: float
    trend: str                    # improving / declining / stable
    effective_roi: float          # 考虑返工后的 ROI
    value_per_token: float        # 每 token 价值

class ROICalculator:
    def __init__(self, cost_tracker, value_meter, rework_tracker=None)
    
    def agent_roi(self, agent_id, window_hours=24) -> ROIResult
    def task_roi(self, task_id) -> ROIResult
    def organization_roi(self, window_hours=168) -> ROIResult
    def compare_agents(self, agent_ids, window_hours=24) -> list[ROIResult]
    def roi_trend(self, agent_id, window_hours=168) -> list[tuple[float, float]]
```

#### 0E — ReworkTracker（新增 `src/maref/recursive/rework_tracker.py`）

跟踪返工成本，调整 ROI 中的 "有效价值"。

```python
@dataclass
class ReworkRecord:
    task_id: str
    original_cost: float
    detection_cost: float
    rework_cost: float
    rework_count: int
    root_cause: str               # precondition/quality/timeout
    
class ReworkTracker:
    def record_rework(self, task_id, rework_cost, root_cause) -> None
    def effective_value(self, task_id, raw_value) -> float  
        # effective = raw_value * (1 / (1 + rework_count))
    def task_rework_cost(self, task_id) -> float
    def agent_rework_rate(self, agent_id) -> float  
        # 一次通过率
```

**Phase 0 验收标准**:
- ValueMeter 可为每种操作记录 value
- BenefitProfile 可计算能力预计价值
- CostTracker 可同时查 cost + value + ROI
- ROICalculator 可输出 agent-level + task-level ROI
- ReworkTracker 可计算有效 ROI = value / (cost + rework_cost)

---

### Phase 1：Execution Intervention（执行中价值干预）

**目标**: 在 token 正在烧的时候保护价值，而非事后算账。

#### 1A — StreamingROIGate（新增 `src/maref/recursive/streaming_roi_gate.py`）

执行中实时评估 ROI 信号，决定继续/切换策略/终止。

```python
@dataclass
class StreamingROIAssessment:
    operation_type: str
    cumulative_cost: float
    cumulative_value: float
    current_roi: float
    progress_signal: float          # 0-1, 当前产出进展信号
    verdict: str                    # continue / re_evaluate / halt
    suggestion: str                 # 建议动作

class StreamingROIGate:
    def __init__(self, cost_tracker, value_meter, 
                 gate_config=None)
    
    def assess(self, operation_type, cost_so_far, value_so_far, 
               progress_signal=0.0) -> StreamingROIAssessment
        # 规则:
        # - 如果 cost > threshold 且 value < threshold: re_evaluate
        # - 如果 cost > critical 且 value == 0: halt
        # - 如果连续 N 步 progress_signal 无增长: re_evaluate
    
    def should_interrupt(self, assessment) -> bool
    def suggest_model_downgrade(self, assessment) -> bool
```

Gate Config 默认值:
```python
ROI_GATE_CONFIG = {
    "min_acceptable_roi": 0.1,      # 低于此值触发 re_evaluate
    "stall_window": 3,               # 连续 N 步无进展触发
    "cost_before_check": 0.5,        # 消耗此比例预算后首次检查
    "critical_zero_value_gap": 0.3,  # 消耗 >30% 预算仍未产出 → halt
    "re_evaluate_max_attempts": 2,   # 最多 re_evaluate 次数
}
```

#### 1B — ProgressiveEscalation（改造 `gateway_adapter.py`）

先计划后执行：先用廉价模型出方案，确认方向后再用强模型。

```python
class ProgressiveEscalation:
    def __init__(self, gateway, streaming_gate)
    
    def execute(self, task, plan_model="cheap", exec_model="premium"):
        # 1. 用廉价模型生成执行 plan
        # 2. 评估 plan 质量分
        #    - 如果 < threshold → 换一个廉价模型重试
        #    - 如果 ≥ threshold → 用 plan 指导执行
        # 3. 用强模型按 plan 执行
        # 4. StreamingROIGate 实时监控执行
```

集成到 `PERCVGatewayAdapter`：
```python
def chat_with_escalation(self, messages, role=GatewayRole.PRIMARY):
    """自动渐进执行：先 plan 后 execute"""
```

#### 1C — Mid-Task Re-plan（改造 `state_machine.py`）

在 FSM ACT 态中插入 `RE_EVALUATE` 子循环。

```python
# GovernanceState 增加:
#   RE_EVALUATE = "re_evaluate"

# GovernanceStateMachine 的 transition 逻辑改造:
#   ACT → RE_EVALUATE 当 StreamingROIGate 触发
#   RE_EVALUATE → ACT 当换策略后继续
#   RE_EVALUATE → HALT 当无法挽回

# 新增方法:
def re_evaluate(self, reason="") -> bool
    """从 ACT 转入 RE_EVALUATE 以重新评估执行策略"""
```

**Phase 1 验收标准**:
- StreamingROIGate 在执行中拦截低 ROI 操作
- ProgressiveEscalation: 先廉价 plan 再强模型执行
- FSM 支持 ACT ↔ RE_EVALUATE 子循环
- 一次性返工率降低信号可追踪

---

### Phase 2：Incentive Governance（行为经济学治理）

**目标**: 从组织行为层面防止 "AI theater"——为烧 Token 而烧 Token。

#### 2A — AITheaterDetector（新增 `src/maref/governance/ai_theater_detector.py`）

检测组织中 "形似产出实则无用" 的行为模式。

```python
@dataclass
class TheaterFlag:
    agent_id: str
    pattern_type: str                # useless_code / overgeneration / 
                                     # repeated_impl / vanity_generation
    description: str
    severity: str                    # WARNING / HIGH / CRITICAL
    metrics: dict[str, float]
    evidence: list[str]

class AITheaterDetector:
    def __init__(self, cost_tracker, credit_rating_system)
    
    def check_all(self) -> list[TheaterFlag]:
        return (
            self._check_code_commit_ratio() +      # 生成 vs 合并比
            self._check_overgeneration() +          # 过量生成
            self._check_repeated_implementation() + # 重复实现
            self._check_vanity_tokens() +           # 无意义消耗
            self._check_token_rank_gaming()         # 打榜行为
        )
    
    def _check_code_commit_ratio(self, threshold=0.2) -> list[TheaterFlag]:
        """检测: committed_code / generated_code < threshold"""
    
    def _check_overgeneration(self, min_unique_tasks=10, max_completion=0.3) -> list[TheaterFlag]:
        """检测: 大量任务但完成率极低"""
    
    def _check_repeated_implementation(self, task_similarity=0.85) -> list[TheaterFlag]:
        """检测: 同一功能反复用不同方式实现"""
    
    def _check_vanity_tokens(self, high_model_pct=0.7, roi_baseline=0.1) -> list[TheaterFlag]:
        """检测: 长期用强模型做低价值任务"""
    
    def _check_token_rank_gaming(self, 
                                  weekend_pattern=True,
                                  low_value_window=True) -> list[TheaterFlag]:
        """检测: 为内部排名而刷 Token"""
```

#### 2B — TokenEconomyMonitor（新增 `src/maref/governance/token_economy_monitor.py`）

组织级 Token 消耗分布监控。

```python
@dataclass
class EconomyReport:
    total_consumption: float
    distribution: dict[str, float]   # 按任务类型
    concentration_index: float       # 集中度
    top_n_agents: list[tuple[str, float]]
    waste_estimate: float            # 估算浪费量
    efficiency_score: float          # 0-1

class TokenEconomyMonitor:
    def __init__(self, cost_tracker, theater_detector)
    
    def report(self) -> EconomyReport:
        # 分析 Token 消耗在各任务类型的分布
        # 识别过度集中在低价值类型的趋势
        # 跨团队/部门比较 ROI
    
    def distribution_by_task_type(self) -> dict[str, float]
    def distribution_by_model_tier(self) -> dict[str, float]
    def concentration_warning(self, gini_threshold=0.6) -> bool
```

#### 2C — AntiGoodhartROI（改造 `inference/memory_trust.py` 或新增）

ROI 数据的 Anti-Goodhart 保护——防止 "ROI 成为 KPI 后 ROI 就不可信"。

```python
class AntiGoodhartROI:
    def __init__(self, roi_calculator, cost_tracker)
    
    def audit_roi_reporting(self, agent_id) -> dict:
        # 校验 ROI 上报数据与实际交付的统计一致性
        # 检测 "选择性上报高 ROI 任务、隐藏低 ROI 任务"
        # 对比 reported_roi vs computed_roi
    
    def gaming_detection(self, window_hours=168) -> list[str]:
        # Pearson 相关性分析: 行为质量 vs ROI 得分的偏离
        # 如果 ROI 持续高但观测到的质量指标没有同步提升
```

**Phase 2 验收标准**:
- AITheaterDetector 可检出 5 种 AI theater 模式
- TokenEconomyMonitor 可输出组织级分布报告
- AntiGoodhartROI 可检测 ROI 数据 gaming
- 触发告警时可联动 Trigram 治理（发现 theater → 降 trust → 限权）

---

### Phase 3：Intelligent Allocation（智能资源分配）

**目标**: 将 ROI 信号接入调度和预算系统，实现价值驱动的资源分配。

#### 3A — 价值感知调度（改造 `dispatcher.py`）

AgentDispatcher 新增 `value_per_token` 维度。

```python
class AgentDispatcher:
    # _dimension_weights 增加:
    #   "value_per_token": 0.10,     # 新增
    #   同时调整现有权重:
    #   "capability_match": 0.30,    # 原 0.35
    #   "performance_history": 0.25, # 原 0.30
    #   "trust_score": 0.20,         # 不变
    #   "current_load": 0.10,        # 不变
    #   "specialization": 0.05,      # 不变
    #   新增 0.10 → 总和仍为 1.0
    
    def __init__(self, ..., roi_calculator=None):
        self._roi_calculator = roi_calculator
        # ...
    
    def _evaluate_match(self, did, task, caps) -> dict:
        # ... 现有维度 ...
        
        # 新增: value_per_token
        value_per_token = 0.5
        if self._roi_calculator:
            roi = self._roi_calculator.agent_roi(did.did_string, window_hours=168)
            value_per_token = min(1.0, roi.value_per_token * 10)
        
        return {
            "capability_match": capability_match,
            "performance_history": performance,
            "trust_score": trust_score,
            "current_load": current_load,
            "specialization": specialization,
            "value_per_token": value_per_token,     # 新增
        }
```

#### 3B — 价值感知预算（改造 `budget.py`）

TokenBudgetController 新增基于任务价值分配更多预算的能力。

```python
class BudgetAction(Enum):
    ALLOW = "allow"
    ALLOCATE_MORE = "allocate_more"    # 新增: 高价值任务给更多预算
    DOWNGRADE = "downgrade"
    BLOCK = "block"
    INTERRUPT = "interrupt"

class TokenBudgetController:
    def __init__(self, tier="standard", roi_calculator=None):
        self._roi_calculator = roi_calculator
        # ...
    
    def check_cost_with_value(self, task_id, user_id, estimated_cost, 
                                estimated_value=0.0, roi_confidence=0.0) -> BudgetResult:
        # 基础检查
        base_result = self.check_cost(task_id, user_id, estimated_cost)
        
        # value override: 高 ROI 任务可获得额外预算
        if estimated_value > 0 and base_result.action in (ALLOW, DOWNGRADE):
            roi = estimated_value / max(estimated_cost, 1)
            if roi > self._high_roi_threshold and roi_confidence > 0.7:
                return BudgetResult(
                    action=BudgetAction.ALLOCATE_MORE,
                    reason=f"high ROI task: estimated ROI {roi:.2f}",
                    current_cost=self._user_costs.get(user_id, 0.0),
                    limit=self._max_cost * 1.5,   # 追加 50% 预算
                    suggested_model="premium",
                )
        
        return base_result
```

#### 3C — 任务价值预估（改造 `decomposer.py`）

SubTask 新增 `estimated_value`，TaskDAG 支持价值排序。

```python
@dataclass
class SubTask:
    task_id: str
    description: str
    estimated_complexity: float
    required_capabilities: list[str]
    depends_on: list[str] = field(default_factory=list)
    estimated_value: float = 0.0        # 新增

class TaskDAG:
    # 新增:
    def value_sorted_order(self) -> list[str]:
        """按预估价值 / 复杂度 比排序"""
    
    def critical_value_path(self) -> list[str]:
        """找到 DAG 中价值最高的关键路径"""
```

#### 3D — 模型选择 ROI 感知（改造 `gateway_adapter.py`）

根据预估 ROI 自动选择模型层级。

```python
class PERCVGatewayAdapter:
    def select_model_by_roi(self, task_roi, task_complexity) -> GatewayRole:
        # ROI 高 + 复杂度高 → PRIMARY
        # ROI 中 + 复杂度中 → STANDARD  
        # ROI 低 + 复杂度低 → CHEAP
        # ROI 低 + 复杂度高 → CHEAP (ROI driven, 不值得投入强模型)
        # ROI 高 + 复杂度低 → STANDARD (强模型浪费)
        pass
    
    def chat_with_roi_selection(self, messages, task_roi=0.0, 
                                  task_complexity=0.5) -> GatewayResponse:
        role = self.select_model_by_roi(task_roi, task_complexity)
        return self.chat(messages, role=role)
```

**Phase 3 验收标准**:
- Dispatcher 优先分配高 ROI agent
- BudgetController 可以为高价值任务追加预算
- SubTask 含价值预估，DAG 支持价值排序
- Gateway 可根据 ROI 自动选模型

---

### Phase 4：Value Ecosystem（价值生态体系）

**目标**: 覆盖知识复用、多 Agent 协作和投资组合级的价值管理。

#### 4A — KnowledgeCapitalROI（新增 `src/maref/recursive/knowledge_capital.py`）

追踪知识工件的复用价值，回溯增加原始任务的 value。

```python
@dataclass
class KnowledgeArtifact:
    artifact_id: str
    source_task_id: str
    source_agent_id: str
    artifact_type: str              # pattern / signal / reusable_code
    value_delivered: float
    created_at: float

@dataclass  
class ArtifactAttribution:
    artifact_id: str
    reference_count: int
    cumulative_reference_value: float
    attributed_agents: list[str]

class KnowledgeCapitalTracker:
    def register_artifact(self, task_id, agent_id, artifact_type, 
                           initial_value) -> str
    
    def record_reference(self, artifact_id, referencer_task_id)
        # 当其他 agent 使用该工件时，回溯增加源 value
    
    def get_attribution(self, agent_id) -> float
        # agent 产出的知识被复用的总价值
```

#### 4B — CollaborationROI（新增 `src/maref/recursive/collaboration_roi.py`）

度量多 Agent 协作的价值和成本。

```python
@dataclass
class CollaborationMetrics:
    dag_id: str
    agent_count: int
    individual_rois: list[float]
    combined_output_value: float
    collaboration_value: float        # combined - sum(individual)
    collaboration_overhead: float     # 同步/协调成本
    net_collaboration_roi: float      # 协作净 ROI

class CollaborationROITracker:
    def measure(self, dag_id, task_rois) -> CollaborationMetrics
        # 协作价值 = 总产出 - 个体独立产出之和
        # 协作成本 = handoff 成本 + 同步成本 + 冲突解决成本
        # 净协作 ROI = (协作价值 - 协作成本) / 协作成本
    
    def optimal_team_size(self, task_type) -> int
        # 从历史数据分析不同类型任务的最优 agent 数
```

#### 4C — ROIPortfolioOptimizer（新增 `src/maref/recursive/portfolio_optimizer.py`）

跨任务组合优化——给定有限预算，选择 ROI 最高的任务组合。

```python
@dataclass
class PortfolioAllocation:
    task_id: str
    predicted_roi: float
    confidence: float
    cost: float
    allocated: bool
    priority: int

class ROIPortfolioOptimizer:
    def __init__(self, roi_forecast, budget_controller)
    
    def optimize(self, pending_tasks: list[SubTask], 
                 available_budget: float) -> list[PortfolioAllocation]:
        # 1. 对每个待办任务预测 ROI
        # 2. 按 predicted_roi * confidence 排序
        # 3. 从高到低分配预算
        # 4. 超出预算的任务标记为 unallocated
        # 5. 返回排序后的分配方案
    
    def marginal_compare(self, new_task, current_lowest_allocated) -> bool:
        # 新任务 ROI > 当前已分配的最低 ROI 任务 → 替换
```

#### 4D — OpportunityCostEngine（新增 `src/maref/recursive/opportunity_cost.py`）

追踪 "不做某事" 的成本和预算到期风险。

```python
@dataclass
class OpportunityCostReport:
    task_id: str
    cost_of_inaction: float           # 不做此事的时间成本
    budget_expiry: float              # 预算到期时间
    urgency_score: float              # 0-1 紧迫度
    recommendation: str               # accept / defer / reject

class OpportunityCostEngine:
    def evaluate(self, task, budget_expiry_days=30) -> OpportunityCostReport
        # 如果预算即将到期，降低价值门槛
        # 有些任务（安全、合规）即使 ROI 不高也不应跳过
```

**Phase 4 验收标准**:
- 知识复用被追踪并可归因
- 多 Agent 协作 ROI 可度量
- Portfolio Optimizer 能在多任务间做价值排序和预算分配
- Opportunity Cost 纳入决策

---

### Phase 5：Governance Enhancement（治理增强）

**目标**: 将 ROI 信号注入 MAREF 核心治理机制。

#### 5A — GovernanceFSM OPTIMIZE 态（改造 `state_machine.py` 和 `constants.py`）

在 STABILIZE 和 REPORT 之间插入 OPTIMIZE 态。

```python
# constants.py:
#   GRAY_CODE: 新增第 10 个状态
#   10: (1, 0, 0, 0, 1) → OPTIMIZE (扩展为 5-bit 或复用)
#
# 方案 A (推荐): 不增加 Gray code 状态，而是在 REPORT 态内
# 增加一个子模式:
#   REPORT 态的行为升级 → 在 REPORT 之前插入 value_optimization 回调

# state_machine.py:
class GovernanceStateMachine:
    def optimize(self, roi_data) -> bool:
        """在 REPORT 之前执行价值优化决策"""
        # 1. 评估刚完成任务的 ROI
        # 2. 更新 agent 的信任分（ROI 因子）
        # 3. 调整后续任务的预算分配
        # 4. 记录优化决策到审计日志
```

#### 5B — CircuitBreaker ROI 模式（改造 `state_machine.py` 中的 `CircuitBreaker`）

不仅看错误率，还看 ROI。

```python
class ROIAwareCircuitBreaker:
    def __init__(self, ..., roi_calculator=None):
        # ...
        self._roi_threshold = 0.05     # ROI 低于此值触发开断
        self._roi_window = 24          # 小时
        self._roi_trip_count = 0
    
    def check_and_trip(self, agent_id) -> bool:
        # 现有: 错误率检查
        # 新增: ROI 检查
        roi = self._roi_calculator.agent_roi(agent_id, self._roi_window)
        if roi.roi_ratio < self._roi_threshold:
            self._roi_trip_count += 1
            if self._roi_trip_count >= 3:
                self.trip(reason=f"ROI below threshold for agent {agent_id}")
                return True
        else:
            self._roi_trip_count = 0
        return False
```

#### 5C — 经济权限作用域（改造 `four_phase_governance.py`）

新增 `BUDGET_AUTONOMY` 经济权限。

```python
# 现有权限:
#   FULL_AUTONOMY, SELF_EVOLUTION, SELF_HEALING, SELF_OPTIMIZATION, 
#   OBSERVATION_ONLY, QUARANTINE

# 新增:
#   BUDGET_AUTONOMY — agent 可自主选择模型和分配预算
#   只在 OLD_YANG + 高 ROI 时授予
#   OLD_YIN / 低 ROI → 预算完全由治理层控制

# Phase 映射改造:
PhasePermissions = {
    Phase.OLD_YANG: [FULL_AUTONOMY, BUDGET_AUTONOMY, SELF_EVOLUTION, 
                     SELF_HEALING, SELF_OPTIMIZATION],
    # OLD_YANG 且 ROI > 0.2 才享有 BUDGET_AUTONOMY
    
    Phase.OLD_YIN: [OBSERVATION_ONLY, QUARANTINE],
    # OLD_YIN 下预算完全由治理层分配
}
```

#### 5D — Trigram ROI Adaptation（改造 `eight_trigrams_governance.py`）

ROI 因子影响信任分 → 自动切换治理模式。

```python
class EightTrigramsGovernance:
    def update_trust_with_roi(self, agent_id, roi_result: ROIResult):
        """将 ROI 因子融入信任分更新"""
        roi_factor = 0.0
        if roi_result.roi_ratio > 1.0:
            roi_factor = 0.1    # ROI > 1 → 信任加分
        elif roi_result.roi_ratio < 0.1:
            roi_factor = -0.1   # ROI < 0.1 → 信任减分
        
        new_trust = self._trust_scores.get(agent_id, 0.5) + roi_factor
        self.update_trust_and_adapt(agent_id, new_trust)
```

#### 5E — CostForecast 重写（改造 `cost_tracker.py` 中的 `CostForecast`）

加入 value 预测，输出 Expected ROI。

```python
class CostForecast:
    def predict_with_value(self, task_description, capabilities, 
                           task_type="") -> tuple[CostEstimate, ValueEstimate]:
        """同时输出预计成本和预计价值"""
        
    @dataclass 
    class ValueEstimate:
        task_description: str
        estimated_value: float
        confidence: float
        similar_tasks_found: int

# 同时新增 ROIForecast:
@dataclass
class ROIForecastResult:
    task_id: str
    task_type: str
    predicted_cost: float
    predicted_value: float
    predicted_roi: float
    confidence: float
    similar_tasks_avg_roi: float

class ROIForecast:
    """基于历史 ROI 数据的预测模型"""
    def predict(self, task) -> ROIForecastResult
    def learn(self, task_id, actual_roi) -> None
    def best_practice(self, task_type) -> dict
        # 返回该类型任务的最优模型/agent 组合
```

#### 5F — ROI Audit Integration（改造 `governance/audit.py` 和 `recursive/unified_audit.py`）

ROI 记录进入审计日志。

```python
# 审计日志新增事件类型:
#   roi_computed
#   roi_warning  
#   roi_critical
#   budget_reallocated
#   ai_theater_detected
#   model_downgraded_by_roi

# UnifiedAuditStore 新增查询:
def query_by_roi_range(self, min_roi, max_roi, window_hours=168)
def query_roi_anomalies(self, threshold=0.1)
def roi_timeline(self, agent_id, window_hours=720)
```

#### 5G — ROI Dashboard（GUI 新增组件）

`gui/src/components/ROI/` 目录：

```typescript
// 组件清单:
// - ROISummary.tsx       —— 组织级 ROI 总览
// - AgentROIChart.tsx    —— agent ROI 对比
// - ROITrendChart.tsx    —— ROI 趋势
// - TokenEconomyPie.tsx  —— Token 分布
// - TheaterDetectionList.tsx —— AI 剧场行为告警
// - PortfolioView.tsx    —— 任务组合优化
// - ReworkHeatmap.tsx    —— 返工率热力图
```

**Phase 5 验收标准**:
- CircuitBreaker 可因 ROI 过低跳闸
- OPTIMIZE 态/回调嵌入 FSM 流程
- Trigram 治理受 ROI 影响
- CostForecast 预测 value 和 ROI
- 审计日志含 ROI 事件
- GUI Dashboard 可视 ROI + Theater + Economy

---

## 三、文件变更清单

### 新增文件

| # | 文件路径 | 代码量(行) | 内容 |
|---|---------|-----------|------|
| 1 | `src/maref/recursive/value_meter.py` | ~100 | ValueMeter + ValueRecord |
| 2 | `src/maref/recursive/roi_calculator.py` | ~200 | ROICalculator + ROIResult |
| 3 | `src/maref/recursive/rework_tracker.py` | ~120 | ReworkTracker + ReworkRecord |
| 4 | `src/maref/recursive/streaming_roi_gate.py` | ~150 | StreamingROIGate + GateConfig |
| 5 | `src/maref/governance/ai_theater_detector.py` | ~200 | 5 种 theater 模式检测 |
| 6 | `src/maref/governance/token_economy_monitor.py` | ~150 | 组织级分布监控 |
| 7 | `src/maref/governance/anti_goodhart_roi.py` | ~100 | ROI gaming 检测 |
| 8 | `src/maref/recursive/knowledge_capital.py` | ~150 | 知识复用追踪 |
| 9 | `src/maref/recursive/collaboration_roi.py` | ~100 | 多 Agent 协作 ROI |
| 10 | `src/maref/recursive/portfolio_optimizer.py` | ~150 | 任务组合优化 |
| 11 | `src/maref/recursive/opportunity_cost.py` | ~100 | 机会成本引擎 |
| 12 | `src/maref/recursive/roi_forecast.py` | ~150 | ROI 预测学习 |
| **新增合计** | | **~1520** | |

### 改造文件

| # | 文件路径 | 改动类型 | 影响行数 |
|---|---------|---------|---------|
| 1 | `capability_contracts.py` | BenefitProfile 新增 | ~20 |
| 2 | `cost_tracker.py` | CostRecord + CostTracker 增加值 | ~30 |
| 3 | `budget.py` | BudgetAction.ALLOCATE_MORE + check_value | ~40 |
| 4 | `dispatcher.py` | value_per_token 维度 + roi_calculator 引用 | ~25 |
| 5 | `decomposer.py` | SubTask.estimated_value | ~5 |
| 6 | `state_machine.py` | RE_EVALUATE + optimize 回调 | ~30 |
| 7 | `governance/constants.py` | OPTIMIZE 映射 | ~5 |
| 8 | `four_phase_governance.py` | BUDGET_AUTONOMY 权限 | ~15 |
| 9 | `eight_trigrams_governance.py` | ROI 信任因子 | ~10 |
| 10 | `gateway_adapter.py` | ROI 模型选择 + 渐进执行 | ~40 |
| 11 | `cost_monitor.py` | 价值感知阈值 | ~20 |
| 12 | `governance/audit.py` | ROI 事件类型 | ~10 |
| 13 | `recursive/unified_audit.py` | ROI 查询 | ~15 |
| 14 | `inference/memory_trust.py` | AntiGoodhartROI 集成 | ~10 |
| **改造合计** | | | **~275** |

---

## 四、依赖关系

```
Phase 0 ─────────────────────────────────────────────────────
  │                                                          
  ├─► Phase 1 (依赖 ValueMeter + ROICalculator)             
  │                                                          
  ├─► Phase 2 (依赖 CostTracker + ROICalculator)            
  │                                                          
  ├─► Phase 3 (依赖 ROICalculator + ReworkTracker)          
  │                                                          
  └─► Phase 4 (依赖 Phase 0 + Phase 1 + Phase 3)           
       │                                                     
       └─► Phase 5 (依赖 Phase 0-4 全部)                    
```

允许**跳跃依赖**（Phase 5 的某些子项可先于 Phase 4 完成）：
- 5D（Trigram ROI Adaptation）仅需 Phase 0 → 可早期实施
- 5A（OPTIMIZE 态）仅需 Phase 1 → 可早期实施
- 5E（CostForecast 重写）仅需 Phase 0 → 可早期实施

---

## 五、测试计划

### 单元测试

| 测试文件 | 测试内容 | 预估用例数 |
|---------|---------|-----------|
| `tests/recursive/test_value_meter.py` | ValueMeter 基础功能 | 15 |
| `tests/recursive/test_roi_calculator.py` | ROI 计算 + 聚合 | 20 |
| `tests/recursive/test_rework_tracker.py` | 返工追踪 + 有效 ROI | 12 |
| `tests/recursive/test_streaming_roi_gate.py` | 实时拦截逻辑 | 18 |
| `tests/recursive/test_portfolio_optimizer.py` | 组合优化 | 10 |
| `tests/recursive/test_knowledge_capital.py` | 知识归因 | 10 |
| `tests/recursive/test_collaboration_roi.py` | 协作度量 | 8 |
| `tests/recursive/test_roi_forecast.py` | ROI 预测 | 12 |
| `tests/governance/test_ai_theater_detector.py` | 5 种 theater 模式 | 20 |
| `tests/governance/test_token_economy_monitor.py` | 分布监控 | 10 |
| `tests/governance/test_anti_goodhart_roi.py` | Gaming 检测 | 8 |
| `tests/executor/test_budget_roi.py` | 价值感知预算 | 12 |
| `tests/executor/test_dispatcher_roi.py` | 价值感知调度 | 8 |
| `tests/governance/test_state_machine_roi.py` | OPTIMIZE 态 | 10 |
| `tests/governance/test_circuit_breaker_roi.py` | ROI 跳闸 | 8 |
| `tests/governance/test_four_phase_econ.py` | 经济权限 | 6 |
| **合计** | | **~187** |

### 集成测试

| 测试文件 | 内容 |
|---------|------|
| `tests/integration/test_roi_governance_flow.py` | 完整流程：Task → Dispatched → Executed → ROI Calculated → Governance Adjusts |
| `tests/integration/test_ai_theater_to_trigram.py` | Theater 检测 → Trust 下调 → Trigram 降级 → Budget 受限 |
| `tests/integration/test_portfolio_budget_cycle.py` | 组合优化 → 预算分配 → 执行 → ROI 反馈 → 下一轮优化 |

---

## 六、里程碑与时间估计

| 里程碑 | 内容 | 预计工作量 | 阶段 |
|-------|------|-----------|------|
| M1 | ValueMeter + BenefitProfile + ReworkTracker + ROICalculator | ~2 天 | P0 |
| M2 | StreamingROIGate + ProgressiveEscalation + RE_EVALUATE | ~2 天 | P1 |
| M3 | AITheaterDetector + TokenEconomyMonitor + AntiGoodhartROI | ~1.5 天 | P2 |
| M4 | Dispatcher ROI + Budget value-aware + SubTask value + Model ROI | ~2 天 | P3 |
| M5 | KnowledgeCapital + CollaborationROI + Portfolio + OpportunityCost | ~2 天 | P4 |
| M6 | OPTIMIZE态 + CircuitBreakerROI + EconPermission + TrigramROI + Forecast + Audit + Dashboard | ~3 天 | P5 |

---

## 七、关键设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| ROI 公式 | `value / cost` vs 加权多维 | `value / cost` | 简洁、可解释、对称于现有 cost 体系 |
| Value 来源 | 自动推导 vs 人工标记 | 两者 | BenefitProfile 预注册 + 执行后可调 |
| 返工调整 | 减法 vs 除法 | 除法: `value * (1/(1+n))` | 随返工次数指数衰减 |
| OPTIMIZE 态 | 新增 FSM 状态 vs REPORT 内子模式 | REPORT 内子模式 | 不破坏现有 10 态 Gray code |
| ROI 跳闸 | 硬跳闸 vs 软提示 | 软提示 3 次后硬跳闸 | 避免单次低 ROI 误判 |
| 经济权限 | 新 Phase vs Phase 内细粒度 | Phase 内细粒度 | 避免 Phase 爆炸 |
| Portfolio 触发 | 定时触发 vs 任务入队触发 | 任务入队触发 | 实时响应新任务 |

---

## 八、风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| Value 度量不准确 | ROI 计算偏差 | 中 | Multiple value sources + AntiGoodhart |
| Theater 检测误报 | 误伤正常 agent | 低 | 软告警 + 人工复核 |
| OPTIMIZE 态增加 FSM 复杂度 | 状态爆炸 | 低 | 采用子模式而非新增状态 |
| Portfolio Optimizer 过杀低 ROI 但必要任务 | 安全/合规任务被跳过 | 中 | "必须执行" 标签豁免 |
| 新增 1520 行代码的测试覆盖 | 低测试覆盖率 | 中 | 187 个测试用例 P0-5 配套 |
