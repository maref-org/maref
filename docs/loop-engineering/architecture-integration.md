# MAREF × Loop Engineering 集成架构蓝图

> **版本**：v0.36.0-rc
> **日期**：2026-07-13
> **审计关联**：[loop-engineering-audit-20260713.md](../loop-engineering-audit-20260713.md)
> **实现位置**：`src/maref/governance/cross_validator.py`

本文档用 Mermaid 描述 Loop Engineering 五要素与 MAREF 三层治理的完整数据流，标注本次审计新增的 3 个 P0 组件（**独立 critic 池 / 硬停止闸门 / epsilon 去重**）。

---

## 一、整体架构总览

```mermaid
flowchart TB
    subgraph User["用户层"]
        HU[Human User]
        HG[Human Gate<br/>RSI-RL-001]
    end

    subgraph Loop["Loop Engineering 五要素"]
        L1[1. 任务地图<br/>Task Map]
        L2[2. 并行/串行调度<br/>Scheduler]
        L3[3. 子 AI 执行<br/>Sub-AI Executor]
        L4[4. 监工验收<br/>Supervisor Review]
        L5[5. 闭环迭代<br/>Loop Iteration]
    end

    subgraph MAREF["MAREF 治理底座 (G1-G5)"]
        G1[G1 MetaCognitiveAuditor<br/>元认知审计]
        G2[G2 SubgoalInterceptor<br/>子目标拦截]
        G3[G3 SocialImpactAssessor<br/>社会影响]
        G4[G4 EconomicGovernor<br/>经济治理]
        G5[G5 CrossInstanceGovernor<br/>跨实例一致性]
    end

    subgraph New["🔴 本次审计新增 P0 组件"]
        CV[CrossValidator<br/>独立 critic 池]
        HS[HardStopGate<br/>硬停止闸门]
        BD[BreakthroughDeduplicator<br/>epsilon 去重]
    end

    subgraph Infra["基础设施层"]
        CB[CircuitBreaker<br/>深度/震荡熔断]
        OS[OscillationFixLoop<br/>5 阶段修复]
        VC[VerifierConsensus<br/>3 策略投票]
        AL[AuditLogger<br/>HMAC-SHA256]
        SM[GovernanceStateMachine<br/>10 态 Gray Code]
    end

    HU --> HG
    HG -->|审批/拒绝| L1
    L1 --> L2
    L2 --> L3
    L3 --> L4
    L4 -->|不通过返工| L3
    L4 --> L5
    L5 -->|下一轮| L1

    L3 -.执行.-> G2
    L4 -.验收.-> CV
    CV --> VC
    CV --> HS
    CV --> CB
    L5 -.迭代.-> BD

    CV -.审计.-> G1
    HS -.预算.-> G4
    L3 -.多实例.-> G5
    L4 -.副作用.-> G3

    HS -->|/tmp/RSI_HALT| HG
    SM --> CB
    SM --> OS
    CV --> AL
    HS --> AL
    BD --> AL

    style New fill:#ffe6e6,stroke:#d32f2f,stroke-width:2px
    style G1 fill:#e3f2fd,stroke:#1976d2
    style G2 fill:#e3f2fd,stroke:#1976d2
    style G3 fill:#e3f2fd,stroke:#1976d2
    style G4 fill:#e3f2fd,stroke:#1976d2
    style G5 fill:#e3f2fd,stroke:#1976d2
```

---

## 二、单轮循环数据流（最详细）

```mermaid
sequenceDiagram
    autonumber
    participant U as User/HITL
    participant TM as Task Map
    participant EX as Sub-AI Executor
    participant CV as CrossValidator<br/>(🆕 独立 critic 池)
    participant HS as HardStopGate<br/>(🆕 硬停止)
    participant BD as BreakthroughDedup<br/>(🆕 epsilon 去重)
    participant CB as CircuitBreaker
    participant VC as VerifierConsensus
    participant G1 as G1 MetaCognition
    participant G4 as G4 Economic
    participant AL as AuditLogger
    participant ST as State Machine

    U->>TM: 输入任务
    TM->>ST: 状态切到 OBSERVE
    TM->>EX: 派发子任务 (parallel/serial)

    loop N 个 critic
        EX->>CV: 提交产出物
        CV->>VC: 调用 verifier (back-compat)
        VC-->>CV: vote + weight
    end

    CV->>CV: assert_critic_independence
    CV->>G1: 元认知偏差检测
    G1-->>CV: bias_score

    alt 产出物是新指标
        CV->>BD: candidate_breakthrough
        BD->>BD: abs(hist - value) < 1e-3 ?
        BD-->>CV: is_genuine / dedup
    end

    CV->>HS: evaluate(round, score, mas_ts, audit, tokens)
    HS->>HS: 检查 11 类停止条件

    alt 应该停止
        HS-->>U: StopDecision(reason)
        HS->>AL: 写 audit 记录
    else 继续
        CV->>CB: record_success / record_failure
        CB-->>CV: state
        CV->>G4: token 消耗上报
        G4-->>CV: budget_status
        CV->>ST: 状态切到 EVALUATE
        CV-->>EX: passed / failed
    end
```

---

## 三、硬停止闸门决策树（11 类停止条件）

```mermaid
flowchart TD
    Start([HardStopGate.evaluate]) --> S1{1. 哨兵文件<br/>/tmp/RSI_HALT 存在?}

    S1 -->|是| ST1[STOP: SAFETY_SENTINEL<br/>RSI-RL-001]
    S1 -->|否| S2{2. MAS-TS 分数<br/>< 60?}

    S2 -->|是| ST2[STOP: SAFETY_HUMAN_GATE<br/>RSI-RL-004]
    S2 -->|否| S3{3. 状态账本<br/>不一致?}

    S3 -->|是| ST3[STOP: INTEGRITY_STATE_INCONSISTENT]
    S3 -->|否| S4{4. 审计分数<br/>< 5.0?}

    S4 -->|是| ST4[STOP: INTEGRITY_AUDIT_SCORE_LOW]
    S4 -->|否| S5{5. 完美分数<br/>== 1.0?}

    S5 -->|是| ST5[STOP: CONVERGENCE_PERFECT]
    S5 -->|否| S6{6. 连续 5 轮<br/>improvement < 0.01?}

    S6 -->|是| ST6[STOP: CONVERGENCE_NO_IMPROVEMENT<br/>受 RSI-RL-002 min_rounds 保护]
    S6 -->|否| S7{7. round >=<br/>max_rounds?}

    S7 -->|是| ST7[STOP: RESOURCE_ROUNDS]
    S7 -->|否| S8{8. wallclock<br/>> 48h?}

    S8 -->|是| ST8[STOP: RESOURCE_WALLCLOCK]
    S8 -->|否| S9{9. tokens ><br/>50k/cycle?}

    S9 -->|是| ST9[STOP: RESOURCE_TOKEN_BUDGET]
    S9 -->|否| Cont([继续下一轮])

    style ST1 fill:#ffcdd2
    style ST2 fill:#ffcdd2
    style ST3 fill:#ffe0b2
    style ST4 fill:#ffe0b2
    style ST5 fill:#c8e6c9
    style ST6 fill:#c8e6c9
    style ST7 fill:#fff9c4
    style ST8 fill:#fff9c4
    style ST9 fill:#fff9c4
    style Cont fill:#b2dfdb
```

---

## 四、独立 critic 池投票机制

```mermaid
flowchart LR
    subgraph Input["输入"]
        ITEM[产出物 item]
    end

    subgraph Diversity["多样性强制 (3 维度)"]
        D1[1. prompt_template 不同]
        D2[2. model 不同]
        D3[3. temperature 跨度 ≥ 0.1]
    end

    subgraph Critics["独立 critic 池 (≥ 3 个)"]
        C1[critic_1<br/>STANDARD<br/>claude-4 t=0.0]
        C2[critic_2<br/>ADVERSARIAL<br/>gpt-5 t=0.5<br/>'找 3 个问题']
        C3[critic_3<br/>TOOL_BASED<br/>gemini-2 t=0.9<br/>运行 linter/test]
        C4[critic_4<br/>NEGATIVE<br/>claude-4 t=0.7<br/>'找拒绝理由']
    end

    subgraph Assert["assert_critic_independence"]
        A1{重复配置?}
        A2{temperature<br/>跨度 ≥ 0.1?}
        A3{mode<br/>≥ 2 种?}
    end

    subgraph Vote["加权多数决"]
        V1[confidence 加权]
        V2[threshold: 0.5]
    end

    ITEM --> C1
    ITEM --> C2
    ITEM --> C3
    ITEM --> C4

    C1 --> A1
    C2 --> A1
    C3 --> A1
    C4 --> A1

    A1 -->|通过| A2
    A2 -->|通过| A3
    A3 -->|通过| V1

    A1 -->|失败| STOP1[STOP: 独立性违规]
    A2 -->|失败| STOP2[STOP: temperature collapse]
    A3 -->|失败| STOP3[STOP: mode collapse]

    V1 --> V2
    V2 -->|≥ 0.5| PASS[通过]
    V2 -->|< 0.5| FAIL[不通过<br/>返工]

    style STOP1 fill:#ffcdd2
    style STOP2 fill:#ffcdd2
    style STOP3 fill:#ffcdd2
    style PASS fill:#c8e6c9
    style FAIL fill:#fff9c4
```

---

## 五、Epsilon 去重：RSI 48h run 教训修复

```mermaid
flowchart TB
    subgraph Problem["❌ RSI 48h run (PID 91372) 根因"]
        P1[cycle 50: 0.9900]
        P2[cycle 80: 0.9904]
        P3[cycle 110: 0.9901]
        P4[cycle 140: 0.9903]
        P5[cycle 200: 0.9902]
        P_RES[连续 34h metric 卡 0.99<br/>breakthroughs 误报泛滥<br/>MetaRatchet 仅诊断 saturation<br/>未采取实质行动]
    end

    subgraph Fix["✅ 修复方案: BreakthroughDeduplicator"]
        F1[candidate value]
        F2{abs hist - value<br/>&lt; epsilon=1e-3 ?}
        F3[is_genuine = False<br/>写入历史但不算突破]
        F4[is_genuine = True<br/>best_value 更新]
        F5[真实突破<br/>+0.01 级别<br/>才触发报告]
    end

    P1 --> P_RES
    P2 --> P_RES
    P3 --> P_RES
    P4 --> P_RES
    P5 --> P_RES

    P_RES -.教训.-> F1
    F1 --> F2
    F2 -->|是 (噪声)| F3
    F2 -->|否 (真实)| F4
    F4 --> F5

    style P_RES fill:#ffcdd2
    style F3 fill:#fff9c4
    style F5 fill:#c8e6c9
```

---

## 六、与现有模块的关系（向后兼容）

```mermaid
flowchart TB
    subgraph New["🆕 新增 (本次审计)"]
        CrossValidator
        HardStopGate
        BreakthroughDeduplicator
        LLMIndependentCritic
    end

    subgraph Reuse["♻️ 复用 (已存在)"]
        VerifierConsensus
        VerifierRegistry
        CircuitBreaker
        OscillationFixLoop
        BudgetBreaker
        AuditLogger
    end

    subgraph Back["⬇️ 被替代/升级"]
        OldVC[旧的单一 VerifierConsensus<br/>同源 LLM 假设]
        OldBD[旧的 Breakthrough 检测<br/>严格 >= 比较]
        OldStop[旧的 CircuitBreaker 单一 stop<br/>无多维度]
    end

    CrossValidator --> VerifierConsensus
    CrossValidator --> VerifierRegistry
    CrossValidator --> CircuitBreaker
    HardStopGate --> BudgetBreaker
    BreakthroughDeduplicator -.替代.-> OldBD
    CrossValidator -.升级.-> OldVC
    HardStopGate -.补全.-> OldStop

    VerifierConsensus --> AuditLogger
    HardStopGate --> AuditLogger
    CrossValidator --> AuditLogger

    style New fill:#ffe6e6,stroke:#d32f2f,stroke-width:2px
    style Reuse fill:#e8f5e9,stroke:#388e3c
    style Back fill:#fafafa,stroke:#9e9e9e,stroke-dasharray: 5 5
```

---

## 七、三种 Loop 元模式 × MAREF 治理映射

```mermaid
flowchart LR
    subgraph Convergent["收敛型 Loop (Convergent)"]
        C_T[目标: 单调收敛<br/>如: 代码优化]
        C_E[Evaluator: VerifierConsensus]
        C_Stop[Stop: HardStopGate<br/>CONVERGENCE_*]
        C_Tool[工具: 文件 + 测试]
    end

    subgraph Exploratory["探索型 Loop (Exploratory)"]
        E_T[目标: 多样性<br/>如: 方案脑暴]
        E_E[Evaluator: CrossValidator<br/>多 critic 投票]
        E_Stop[Stop: HardStopGate<br/>RESOURCE_WALLCLOCK]
        E_Tool[工具: 搜索 + 只读 DB]
    end

    subgraph Interactive["交互型 Loop (Interactive)"]
        I_T[目标: 用户满意<br/>如: HITL 审批]
        I_E[Evaluator: HITLService<br/>4 级审批]
        I_Stop[Stop: HardStopGate<br/>SAFETY_HUMAN_GATE]
        I_Tool[工具: 知识库 + CRM]
    end

    C_E --> CrossValidator
    E_E --> CrossValidator
    I_E --> HumanGate[Human Gate<br/>RSI-RL-001]

    C_Stop --> HardStopGate
    E_Stop --> HardStopGate
    I_Stop --> HardStopGate

    style CrossValidator fill:#ffe6e6
    style HardStopGate fill:#ffe6e6
    style HumanGate fill:#e3f2fd
```

---

## 八、状态机集成（10 态 Gray Code）

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> OBSERVE: 任务进入
    OBSERVE --> ANALYZE: 上下文完成

    ANALYZE --> EVALUATE: 进入验收
    EVALUATE --> CrossValidate: 调用 CrossValidator

    state CrossValidate <<choice>>
    CrossValidate --> DECIDE: 通过 (passed=True)
    CrossValidate --> ACT: 失败 → 返工

    DECIDE --> ACT: 决策完成
    ACT --> VERIFY: 执行完成
    VERIFY --> STABILIZE: CrossValidator OK
    VERIFY --> ANALYZE: CrossValidator 失败

    STABILIZE --> HardStopCheck
    state HardStopCheck <<choice>>
    HardStopCheck --> REPORT: 应该停止
    HardStopCheck --> OBSERVE: 继续迭代

    REPORT --> HALT: 报告写入
    HALT --> [*]
```

---

## 九、文件落点与导入路径

| 组件 | 文件路径 | 导出符号 |
|------|---------|---------|
| CrossValidator | `src/maref/governance/cross_validator.py` | `CrossValidator`, `CrossValidatorConfig` |
| HardStopGate | 同上 | `HardStopGate`, `StopReason`, `StopDecision` |
| BreakthroughDeduplicator | 同上 | `BreakthroughDeduplicator`, `BreakthroughRecord` |
| IndependentCritic | 同上 | `IndependentCritic`, `LLMIndependentCritic`, `CriticMode`, `CriticVerdict` |
| Independence check | 同上 | `assert_critic_independence` |
| Constants | 同上 | `HARD_STOP_HUMAN_GATE`, `DEFAULT_DEDUP_EPSILON`, `DEFAULT_MAS_TS_FLOOR`, `DEFAULT_MIN_ROUNDS`, `DEFAULT_TOKENS_PER_CYCLE`, `DEFAULT_MAX_WALLCLOCK_HOURS` |

**使用示例**：

```python
from maref.governance import (
    CrossValidator, CrossValidatorConfig,
    HardStopGate, BreakthroughDeduplicator,
    LLMIndependentCritic, CriticMode,
    HARD_STOP_HUMAN_GATE,
)

# 配置硬停止 + 去重
hard_stop = HardStopGate(
    sentinel_path=HARD_STOP_HUMAN_GATE,  # /tmp/RSI_HALT
    min_rounds=10,  # RSI-RL-002
    max_tokens_per_cycle=50_000,
)
dedup = BreakthroughDeduplicator(epsilon=1e-3)

cv = CrossValidator(config=CrossValidatorConfig(
    hard_stop=hard_stop,
    dedup=dedup,
    min_agreement=0.5,
))

# 注册 3 个独立 critic (不同 model/temperature/mode)
cv.register_critics([
    LLMIndependentCritic("c1", "claude-4", "P1 {item}", 0.0, CriticMode.STANDARD),
    LLMIndependentCritic("c2", "gpt-5", "P2 {item}", 0.5, CriticMode.ADVERSARIAL),
    LLMIndependentCritic("c3", "gemini-2", "P3 {item}", 0.9, CriticMode.TOOL_BASED),
])

# 每轮循环调用
result = cv.validate(
    item=output,
    round_num=cycle,
    current_score=score,
    mas_ts_score=mas_ts,
    tokens_used_this_cycle=tokens,
    candidate_breakthrough=score,  # 去重
)

if result.stop.should_stop:
    logger.warning("STOP: %s", result.stop.reason)
    break
```

---

## 十、版本与路线图

| 版本 | Loop Engineering 治理交付 |
|------|---------------------------|
| v0.35.0-rc | 叙事层 + 文档 + 三种元模式架构设计 |
| v0.36.0-rc | `maref.loop` 模块 + CrossValidator (本文档) + HardStopGate + BreakthroughDeduplicator |
| v1.0 | 全栈递归进化 + Agent 信用评级 + 四象治理模型 + 48h 长循环稳定运行验证 |
