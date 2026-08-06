# Interactive Loop Template

> v0.35.0-rc (Spec) → v0.36.0-rc (Implementation)
> 对应 MAREF 组件：`HITLService` · `CarbonSiliconSymbiosis` · `FourPhaseGovernance` · `InterruptProtocol`

---

## 适用场景

- 客服对话 Agent
- 销售/售前咨询
- 教育辅导 / 一对一教学
- HITL 审批工作流
- 医疗问诊辅助
- 任何需要逐轮人类交互的任务

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                   Interactive Loop                           │
│                                                              │
│  INIT → LISTEN → THINK → RESPOND → [done?] → HALT          │
│    │       │         │         │            │                │
│    │       │         │         ▼ yes        │                │
│    │       │         │    用户结束对话       │                │
│    │       │         │                      │                │
│    ▼       ▼         ▼                      ▼                │
│  上下文   人类输入   推理     回复         结束              │
│  初始化   解析      生成    输出           审计              │
│                                                              │
│  安全层: SentimentSafetyValve (用户情绪检测 → 降级/转人工)   │
│          MaxTurns (默认 50 轮)                               │
│          CooldownTimer (同一问题重复 N 次 → 转人工)          │
│                                                              │
│  差异点: 每轮必须等待人类输入                                  │
│          没有"自动重试"                                       │
└──────────────────────────────────────────────────────────────┘
```

**与收敛/探索型的核心区别**：
- 交互型 Loop 每轮控制权在**人类**手中
- Agent 不能自驱进入下一轮
- 输出是对话而非数据/代码

---

## 默认配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_turns` | 50 | 最大对话轮数 |
| `max_tokens_per_turn` | 4096 | 每轮最大输出 Token |
| `sentiment_threshold` | -0.5 | 用户情绪低于此值 → 触发情感安全阀 |
| `repetition_detection_window` | 5 | 检测同一意图重复次数 |
| `repetition_max_count` | 3 | 超过此次数 → 转人工 |
| `human_escalation_timeout` | 300s | 转人工等待超时 → 安全回复 |
| `spot_check_rate` | 0.05 | 5% 抽查率（映射 CarbonSiliconSymbiosis） |

---

## Evaluator 接口

交互型 Evaluator 是"回合评估"而非"产出评估"：

```python
@dataclass
class TurnResult:
    turn_id: int
    user_input: str
    agent_response: str
    sentiment_score: float              # 用户情绪 (-1.0 ~ 1.0)
    intent_match: bool                  # Agent 是否理解用户意图
    knowledge_match: float              # 知识库匹配度 (0~1)
    response_time_ms: int               # 首次响应时间
    requires_escalation: bool           # 是否需要转人工
    metadata: dict[str, Any]

@dataclass
class ConversationSummary:
    turns: list[TurnResult]
    total_turns: int
    resolved: bool                      # 用户是否说"解决了"
    user_satisfaction: float            # 整体满意度 (如有评分)
    escalation_count: int               # 转人工次数
    compliance_issues: list[str]        # 合规检查问题
```

---

## 工具白名单

| 工具域 | 权限 | 说明 |
|--------|------|------|
| 知识库 | READ | 查询 FAQ / 产品信息 / 政策文档 |
| CRM | READ + WRITE | 查询和更新客户信息（需 GDPR 审计） |
| 工单系统 | CREATE | 创建工单，不允许删除 |
| 对话历史 | READ + WRITE | 读写当前对话上下文 |
| LLM | GENERATE | 生成回复 |
| 情感分析 | EXECUTE | 用户情绪检测 |

禁止：文件系统写、代码执行、数据库结构修改、批量导出客户数据。

---

## 停止条件（优先级从高到低）

1. **用户明确结束** — 用户说"再见"/"解决了"/"没事了" → HALT
2. **情感安全阀触发** — `sentiment < threshold` → 降级/转人工 → HALT
3. **重复检测触发** — 同一意图重复 3 次 → 转人工 → HALT
4. **最大轮数** — `turn >= max_turns` → 友好结束 → HALT
5. **静默超时** — 用户超过 N 分钟未回复 → 自动结束 → HALT
6. **合规违规** — 检测到 GDPR/PCI 违规请求 → 拒绝 + 审计 → HALT

---

## MAREF 治理绑定

| 治理层 | 绑定方式 |
|--------|---------|
| 天极 (红线) | `MetaAgentClosure` — 禁止 Agent 冒充人类、禁止承诺无法履行的服务 |
| 人极 (HITL) | `CarbonSiliconSymbiosis` — 5% 抽检 + 转人工升级路径 |
| 地极 (信任) | `TrustBoundaryManager` — CRM 写操作强制审计日志 |
| 经卦 (状态机) | `FourPhaseGovernance` — 根据用户情绪动态调整 Agent 自主度 |
| 别卦 (约束) | `DataSovereignty` — 客户数据不跨域存储 |
| 爻变 (演化) | `ExperiencePool` — 优秀对话案例存入经验池，优化回复策略 |

---

## 代码骨架（v0.36.0-rc 实现目标）

```python
class InteractiveLoop:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        crm: CRMClient,
        sentiment_analyzer: SentimentAnalyzer,
        tool_boundary: ToolBoundary,
        max_turns: int = 50,
        sentiment_threshold: float = -0.5,
    ):
        self._context = ConversationContext()
        self._safety_valve = SentimentSafetyValve(sentiment_threshold)

    async def turn(self, user_input: str) -> AgentResponse:
        self._context.add_user_message(user_input)

        sentiment = self._sentiment_analyzer(user_input)
        if self._safety_valve.should_escalate(sentiment):
            return self._escalate_to_human()

        intent = await self._intent_classifier(user_input)
        knowledge = await self._knowledge_base.query(intent)
        reply = await self._generate_reply(intent, knowledge)

        self._context.add_agent_message(reply)

        if self._should_end_conversation():
            self._finalize()
            return AgentResponse(reply, end_conversation=True)

        return AgentResponse(reply)

    async def run(self, greeting: str) -> ConversationSummary:
        first_reply = AgentResponse(greeting)
        while not first_reply.end_conversation:
            user_input = await self._wait_for_user()
            first_reply = await self.turn(user_input)
        return self._summarize()
```

---

## 现有 MAREF 映射已验证

| 现有组件 | 映射到此模板的位置 |
|----------|-----------------|
| `HITLService` (P0/P1/P2/P3) | 转人工升级路径 |
| `CarbonSiliconSymbiosis` | 5% 抽检 + 人类确认→执行→自审→抽检 |
| `EscalationProposal` + `DeadlineNegotiator` | 超时协商机制 |
| `FourPhaseGovernance` | 信任度自适应（OLD_YANG→…→OLD_YIN） |
| `InterruptProtocol` | 人类中断 Agent 回复 |
| `ExperiencePool` | 优秀对话回存经验池 |
| `DataSovereignty` | 客户数据跨域限制 |
| `Sanitizer` | 输入消毒（防止注入攻击） |

> **注意**：交互型 Loop 是 MAREF 目前覆盖最完整的元模式（得益于 HITL 体系的成熟）。
> v0.36.0-rc 的主要工作是将这些分散的组件统一到 `InteractiveLoop` 接口下，
> 并补齐 `SentimentSafetyValve`、`RepetitionDetector`、`ConversationContext` 等对话专用组件。
