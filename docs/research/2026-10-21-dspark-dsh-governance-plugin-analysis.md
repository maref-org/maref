# DSpark、DeepSeek Harness 与 MAREF 治理插件化分析

> **日期**: 2026-10-21
> **分析对象**: MAREF v0.54.3
> **代码基线**: `0df21744`
> **结论状态**: 研究结论 / DSpark 与 dsh 外部事实待官方核验
> **配套实施方案**: [`docs/plans/2026-10-21-governance-policy-packs.md`](../plans/2026-10-21-governance-policy-packs.md)

---

## 0. 结论摘要

| 问题 | 结论 | 优先级 |
|---|---|---|
| DSpark 是否提升 MAREF 能力 | 不提升智能与治理能力；只改善自托管推理的延迟、吞吐和单位成本 | P2 |
| DSpark 如何接入 | 放在统一 LLM 网关之后，或作为可选的 `ModelAdapter`；不进入治理核心 | P2 |
| dsh 是否值得依赖 | 当前 v0.1 预览，不建议生产依赖；其 Harness/插件/沙箱设计值得借鉴 | P1（借鉴） |
| “治理底座 + 地缘/场景插件”是否可行 | 可行，且已有大半骨架；但需要统一策略模型和插件契约 | P0 |
| 是否需要大规模重构 | 不需要重写核心；需要一次中等规模的策略层改造 | — |
| 最推荐的第一步 | 先做“声明式策略包/合规包”，不做任意代码插件 | P0 |

**核心判断**：MAREF 的护城河不在“再做一个 Agent runtime”，而在**可审计、可证明、可执行的治理控制面**。DSpark 降低运行成本，dsh 提供运行时插件化参考；二者都应服务于“让治理底座更便宜、更可组合”，而不是替代治理底座。

---

## 1. 研究范围与事实边界

### 1.1 已核验的仓库事实

本文对 MAREF 的判断基于当前仓库代码与测试，重点证据见 §7。以下结论均可在对应文件中复核：

- `GovernancePipeline` 已支持外部策略规则注入，但默认规则是硬编码的 Python callable。
- `GovernedPipeline` 组装主治理管线时没有传入 `policy_rules`，也没有接入多法域路由。
- `JurisdictionPolicyRouter` 已存在，并带有 GDPR / China CSL / Five Eyes 规则包；但它主要服务 federation HTTP / federated saga 路径，不在 `GovernedPipeline` 主路径。
- `RegulatoryPolicyMapper` 已能把“动作 × 辖区”映射为 OBSERVE / ADVISORY / ENFORCE，但未接入 `GovernancePipeline` 的实际裁决。
- `OrganizationPolicy` 已支持 YAML 配置驱动的组织/角色/动作策略，是“声明式策略”的现成先例。
- 仓库未发现通用 `entry_points` / `pluggy` 插件加载器；现有动态导入只出现在少数合规检查模块。
- `MarketplaceSkillRegistry` 有 manifest 和三级门禁概念，但其静态扫描是入口字符串启发式，沙箱测试是模拟的，不能直接充当治理插件的安全边界。

### 1.2 未核验的外部事实

以下内容按用户给定的口径分析，**尚未做官方资料核验**：

- DSpark 是半自回归推测解码推理加速框架，DeepSeek-V4 线上提速 60%–85%，已开源并适配 Qwen3。
- DSpark 的 vLLM 集成接口基本兼容，`DSparWrapper` 复用 `generate()`；draft 模型建议为主模型 1/10–1/5，显存约增加 12%–23%。
- DeepSeek Harness（dsh）于 2026-08-13 发布，主张 “Model + Harness = Agent”，当前 v0.1 预览，存在破坏性变更。

> 在对外材料中引用这些数字前，必须补齐官方 release note、benchmark 配置、模型版本和硬件条件；不同 batch size、序列长度、draft 模型质量会显著改变结论。

---

## 2. DSpark：成本/延迟杠杆，不是治理升级

### 2.1 DSpark 解决的是什么问题

DSpark 位于**推理服务层**，不是 Agent 框架层。它的价值成立需要满足：

1. 模型自托管；
2. 推理后端支持 speculative decoding / draft model；
3. 负载足够大，能够摊薄 draft 模型显存和调度开销；
4. 任务对延迟或吞吐敏感，而不是只对最终质量敏感。

它不解决：

- 治理裁决是否正确；
- 工具调用是否安全；
- 多 Agent 协作是否可审计；
- 合规证据是否完整；
- 模型选择是否合规。

### 2.2 对 MAREF 的真实收益

MAREF 的高价值场景是递归进化、SAEB、批量评估、长链路 Agent。这些场景会重复调用模型，因此推理加速有**乘数效应**：

- 降低 TTFT 和 p95 延迟；
- 提高单卡吞吐，降低自托管单位成本；
- 缩短递归循环的 wall-clock 时间；
- 让更多评估轮次在相同预算内完成。

但收益是**有条件的**：

- 如果使用 DeepSeek 托管 API，MAREF 无法控制服务端是否启用 DSpark；
- 如果走第三方 OpenAI 兼容 API，DSpark 只影响服务端，MAREF 侧无需改代码；
- 如果本地 GPU 显存紧张，draft 模型的额外显存可能抵消收益；
- 如果任务以工具调用/编排为主，模型推理不是瓶颈，收益有限。

### 2.3 MAREF 当前推理调用面

MAREF 目前没有统一推理网关，调用面是分散的：

| 路径 | 现状 | 影响 |
|---|---|---|
| `src/maref/execution/adapters/base.py` | `ModelAdapter` 只有 `complete()` / `model_name` / `count_tokens()` | 抽象过窄，不支持流式、工具调用、usage |
| `src/maref/execution/adapters/local_adapter.py` | 仅 transformers 本地推理 | 不是生产级 vLLM/DSpark 适配 |
| `src/maref/integration/feature_dev/llm_client.py` | 直接走 OpenAI 兼容 `chat/completions` | 换后端需改配置或代码 |
| `src/maref/recursive/skill_executor.py` | 直接创建 OpenAI/Anthropic client | 调用策略分散 |
| `src/maref/recursive/llm_code_generator.py` | 直接创建 OpenAI/Anthropic client | 同上 |
| `src/maref/stress/*` | 各自持有 provider client | 基准与生产路径不一致 |

因此，**只加一个 `DSparkAdapter` 覆盖不了全部调用路径**。正确顺序是：

1. 先收口 LLM 网关（base_url、鉴权、超时、重试、模型路由、计量）；
2. 在网关后接 vLLM + DSpark；
3. 需要离线/本地路径时，再加 `DSparkAdapter(ModelAdapter)`；
4. 用 A/B 数据决定是否默认启用。

### 2.4 建议的接入方式

#### 方案 A：托管 API（推荐默认）

- 不修改 MAREF 代码；
- 通过 `OPENAI_BASE_URL` 指向兼容网关；
- 由网关决定是否启用 DSpark；
- 用现有 `ModelRouteRecorder` / 成本护栏记录实际用量。

#### 方案 B：自托管 vLLM + DSpark（推荐用于高负载）

- 部署 vLLM + DSpark；
- MAREF 统一走 OpenAI 兼容接口；
- 在网关层做模型路由、限流、计量；
- 建立基准：TTFT、tokens/s、p95、显存、单任务成本、SAEB 通过率。

#### 方案 C：本地 `ModelAdapter`（仅离线/边缘）

- 新增 `DSparkAdapter` 实现 `ModelAdapter`；
- 只覆盖使用 `ModelAdapter` 的路径（如 workflow generator）；
- 不假设它能覆盖全部 Agent 调用。

### 2.5 DSpark 结论

- **定位**: P2 可选推理后端，不是治理能力。
- **前置条件**: 统一 LLM 网关。
- **验收指标**: 延迟、吞吐、成本、质量回归，而不是“是否用了 DSpark”。
- **风险**: draft 模型显存、版本耦合、批处理退化、故障模式增加。
- **不做**: 把 DSpark 写进治理核心，或把它当作 Agent 智能升级。

---

## 3. DeepSeek Harness：借鉴运行时契约，不依赖 v0.1

### 3.1 dsh 的核心命题

dsh 的 “Model + Harness = Agent” 把 Agent 拆成可替换部件：

- model adapter
- tool provider
- sandbox
- session / event log
- agent loop
- plugin manifest / lifecycle

这对 MAREF 的启示不是“换框架”，而是：**模型层和运行时层会商品化，治理层和责任层不会。**

### 3.2 MAREF 已有的对应能力

| dsh 概念 | MAREF 对应物 | 状态 |
|---|---|---|
| model adapter | `ModelAdapter`、各 provider client | 有，但分散 |
| harness | `BaseHarness` / `UnifiedHarness` | 有生命周期，缺稳定插件 ABI |
| agent loop | `LoopBase` / `GovernedLoop` / 多种 Loop | 有治理桥，缺统一事件契约 |
| tool provider | `UnifiedToolRegistry`、MCP/A2A | 有注册表，缺能力授权闭环 |
| sandbox | 部分执行/隔离组件 | 有零散能力，缺统一 sandbox contract |
| session log | `AuditLogger`、failure event bus | 有审计，缺统一 Agent 会话事件流 |
| plugin manifest | `SkillManifest`、Marketplace | 有 manifest，但门禁偏弱 |

### 3.3 真正值得抄的四件事

1. **Harness 契约**：把“模型调用、工具调用、沙箱、会话、循环”定义成稳定接口，而不是散落在各模块。
2. **插件生命周期**：安装、启用、禁用、升级、回滚、健康检查、版本兼容。
3. **能力受限沙箱**：文件、网络、进程、凭证必须显式授权；不能靠入口字符串扫描。
4. **会话事件日志**：统一记录 model/tool/sandbox/decision 事件，支持回放和回归。

### 3.4 不建议做的事

- 不把 dsh v0.1 作为生产依赖；
- 不用 dsh 替换 MAREF 的治理控制面；
- 不为“插件化”而重写已经稳定的 `GovernedPipeline`；
- 不把 marketplace 的弱门禁直接升级为治理插件的安全边界。

### 3.5 dsh 结论

- **定位**: P1 架构参考，P3 可选运行时实验。
- **借鉴顺序**: 先 Harness/插件契约，后 sandbox/session log，最后才考虑 agent-loop 插件化。
- **判断标准**: 是否降低治理接入成本、是否提高可审计性、是否保持 fail-closed。

---

## 4. 治理底座 + 地缘/场景插件：可行，但要分层

### 4.1 目标架构

```text
┌─────────────────────────────────────────────────────────┐
│ 核心不变量层（不可被插件覆盖）                          │
│ TrustBoundary · HITL · Audit · Permission · Budget      │
│ DENY 优先 · fail-closed · 策略版本/epoch · HMAC 签名    │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ 政策包层（声明式，可审计，可回滚）                      │
│ 地缘包：EU AI Act / China CSL / GDPR / Five Eyes ...    │
│ 行业包：金融 / 医疗 / 政务 ...                          │
│ 组织包：租户/角色/动作策略（OrganizationPolicy）        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│ 场景能力包层（工具/技能/工作流/评测集）                 │
│ 金融分析 · 医疗问答 · 客服 · 研发 · 内容生产 ...        │
└─────────────────────────────────────────────────────────┘
```

**关键原则**：

- 核心层只增不减：插件可以让裁决更严格，不能让核心 DENY 变 ALLOW。
- 地缘包是**政策数据**，不是任意代码。
- 场景包是**能力扩展**，不能改写治理裁决。
- 所有包必须有版本、来源、哈希、适用法域/租户、审计记录。

### 4.2 现有骨架

#### 4.2.1 可注入的策略规则

`GovernancePipeline` 已接受外部规则：

```python
policy_rules: list[
    tuple[int, Callable[[GovernanceRequest], tuple[Verdict, str, HITLTier | None]]]
] | None = None
```

见 `src/maref/governance/core_pipeline.py:146`、`:184`。这说明“策略可扩展”在核心管线里已有缝，但还缺少：

- 声明式格式；
- 包加载/校验/版本管理；
- 权限边界；
- 与多法域路由的统一。

#### 4.2.2 多法域路由

`JurisdictionPolicyRouter` 已支持：

- 多法域注册；
- 每个法域独立 `FederationPolicyEngine`；
- 冲突策略（含 `MOST_RESTRICTIVE`）；
- 决策日志与 SQLite 持久化。

见 `src/maref/federation/jurisdiction_router.py:154`。

`install_regulatory_rules()` 已内置三套真实规则书，`create_regulatory_router()` 可直接构建：

- `src/maref/federation/jurisdiction_rules.py:340`
- `src/maref/federation/jurisdiction_rules.py:378`

这是“地缘插件”的现成运行时，**不需要另起炉灶**。

#### 4.2.3 监管策略映射

`RegulatoryPolicyMapper` 已把“动作 × 辖区”映射为：

- `OBSERVE`
- `ADVISORY`
- `ENFORCE`

见 `src/maref/compliance/regulatory_policy_mapper.py`、`src/maref/compliance/jurisdiction_profile.py`。

但它是独立映射器，未接入 `GovernancePipeline` 的实际裁决；测试里通过 `parameters={"jurisdiction": "eu"}` 传入辖区，但核心管线并不消费该字段。这说明“有数据模型，没有主路径接线”。

#### 4.2.4 配置化组织策略

`OrganizationPolicy.from_path()` 已支持 YAML 驱动：

```yaml
version: 1
epoch: "2026-10-19"
default_decision: deny
organizations:
  acme:
    roles:
      坎:
        allow: ["file.read"]
        deny: ["payment.*"]
        require_approval: ["file.write"]
```

见 `src/maref/governance/org_policy.py:51`。这是“声明式策略包”的现成先例，说明方向与现有架构兼容。

### 4.3 关键断点

| 断点 | 事实 | 影响 |
|---|---|---|
| 主路径未接策略包 | `GovernedPipeline` 构造 `GovernancePipeline` 时未传 `policy_rules`，也未接 `JurisdictionPolicyRouter` | 多法域能力停留在 federation 路径 |
| 两套规则模型 | core 是 Python callable；federation 是数据驱动 `PolicyRule` | 直接加插件会变成第三套规则 |
| 缺少 no-downgrade 语义 | core 规则按优先级取首个 DENY/ASK_USER；高优先级 ASK_USER 可能先于低优先级 DENY | 插件可能降低核心限制 |
| 缺少包契约 | 没有 manifest、版本兼容、哈希、签名、冲突检测 | 无法安全分发和审计 |
| marketplace 门禁偏弱 | 静态扫描是启发式，沙箱测试是模拟 | 不能作为治理插件安全边界 |

### 4.4 插件分类

#### A. 地缘政策包（Jurisdiction Policy Pack）

内容：

- 适用法域；
- 法规引用；
- 生效日期/版本；
- 动作匹配；
- 裁决（ALLOW / DENY / DEFER）；
- 条件（数据类型、跨境、风险等级、角色等）；
- 证据映射；
- 冲突策略。

运行时：

- 编译为 `GovernancePipeline` 的扩展规则；
- 同步注册到 `JurisdictionPolicyRouter`，供 federation 路径复用；
- 采用 `MOST_RESTRICTIVE` 或显式冲突策略；
- 只能升级限制，不能降级核心裁决。

#### B. 场景能力包（Scenario Capability Pack）

内容：

- 工具；
- 技能；
- 工作流；
- 评测集；
- 行业模板；
- 合规模板。

运行时：

- 走 `UnifiedToolRegistry` / Marketplace / Loop 体系；
- 不直接改写治理裁决；
- 需要能力授权和沙箱约束。

#### C. 运行时插件（Runtime Plugin，后置）

内容：

- model adapter；
- tool provider；
- sandbox；
- session log；
- agent loop。

运行时：

- 需要稳定的 plugin ABI；
- 需要生命周期、隔离、版本兼容、健康检查；
- 这是 dsh 借鉴的最终形态，但不建议在第一阶段做。

### 4.5 安全边界

治理插件必须遵守：

1. **Deny-overrides**：核心 DENY 不能被插件降级。
2. **Fail-closed**：包加载失败、版本不兼容、冲突无法裁决时拒绝启用，而不是静默跳过。
3. **无任意代码**：政策包只允许声明式数据，不允许 `entrypoint`、`eval`、动态导入。
4. **可审计**：每次命中记录 pack id、version、hash、rule id、法规引用。
5. **可回滚**：包版本可切换，旧版本保留审计记录。
6. **最小权限**：包只能声明策略，不能读取凭证、执行网络请求或修改审计日志。
7. **来源验证**：外部包至少校验 SHA-256；生产环境建议 Ed25519 签名 + 允许列表。

---

## 5. 重构规模判断

### 5.1 不需要重写核心

以下组件应保持稳定：

- `GovernancePipeline` 的 8 步主流程；
- `TrustBoundaryManager`；
- `AuditLogger` / HMAC 链；
- `HITLRouter`；
- `PermissionMatrix`；
- `CircuitBreaker` / 预算熔断；
- `GovernedPipeline` 的组织策略、商业动作、证据链。

### 5.2 需要中等规模改造

1. **统一规则模型**：把声明式 `PolicyPackRule` 编译到 core 与 federation 两个消费端。
2. **增加 no-downgrade 合并**：核心裁决先算，扩展规则只能升级。
3. **补齐主路径接线**：`GovernedPipeline` 注入 policy pack registry，按 `jurisdiction` 激活。
4. **补齐审计字段**：pack id/version/hash/rule id/法规引用。
5. **补齐加载与验证**：manifest、版本兼容、冲突检测、文件大小/路径安全。
6. **补齐测试**：deny-overrides、法域隔离、核心回归、federation 一致性。

### 5.3 分阶段

| 阶段 | 内容 | 规模 | 风险 |
|---|---|---|---|
| P0 | 政策包 schema + loader + registry + core 合并语义 | 1–2 周 | 低 |
| P1 | 地缘包接入 `GovernedPipeline` + federation adapter + 审计 | 1–2 周 | 中 |
| P2 | 场景能力包接入工具/技能/工作流 | 2–3 周 | 中 |
| P3 | dsh 式 Harness/Tool/Sandbox/Session 插件 ABI | 独立季度 | 高 |
| P2（独立） | DSpark 统一网关 + 可选 adapter + A/B | 1 周 | 低 |

> 周期是工程估算，不是承诺；实际取决于测试覆盖、包数量和是否需要兼容旧策略。

---

## 6. 决策建议

### 6.1 推荐决策

1. **先做政策包，不做代码插件。**
2. **复用 `JurisdictionPolicyRouter`，不另建地缘引擎。**
3. **在 `GovernedPipeline` 主路径接入 pack registry，但默认不启用任何包，保持现有行为。**
4. **扩展规则只能升级限制，核心 DENY 永远优先。**
5. **DSpark 作为 P2 推理后端，经统一 LLM 网关接入。**
6. **dsh 作为 P1 设计参考，P3 再评估运行时插件化。**

### 6.2 明确不做

- 不在第一阶段做任意第三方代码插件；
- 不让插件覆盖审计、HITL、TrustBoundary、预算熔断；
- 不把 DSpark 当作智能升级；
- 不直接依赖 dsh v0.1；
- 不为插件化重写 `GovernancePipeline`。

### 6.3 成功标准

- 默认配置下，现有治理测试全部通过，行为不变。
- 启用一个地缘包后，同一动作在 EU/CN/global 下产生不同但可解释的裁决。
- 插件包无法把核心 DENY 降级为 ALLOW。
- 每次命中都能从审计日志回溯到 pack id、版本、哈希、规则和法规引用。
- 包加载失败时 fail-closed，并有明确错误。
- federation 路径与主路径对同一包给出一致裁决。

---

## 7. 证据索引

| 主题 | 文件 | 关键点 |
|---|---|---|
| 核心管线规则注入 | `src/maref/governance/core_pipeline.py:146` | `policy_rules` 参数 |
| 默认规则 | `src/maref/governance/core_pipeline.py:198` | 硬编码 Python callable |
| 规则评估 | `src/maref/governance/core_pipeline.py:476` | 按优先级取首个 DENY/ASK_USER |
| 主路径组装 | `src/maref/governance/governed_pipeline.py:232` | 未传 `policy_rules` / jurisdiction |
| 组织策略 YAML | `src/maref/governance/org_policy.py:51` | 声明式策略先例 |
| 多法域路由 | `src/maref/federation/jurisdiction_router.py:154` | 多法域 + 冲突策略 |
| 法规规则包 | `src/maref/federation/jurisdiction_rules.py:340` | GDPR / China CSL / Five Eyes |
| 法规路由构建 | `src/maref/federation/jurisdiction_rules.py:378` | `create_regulatory_router()` |
| 监管映射 | `src/maref/compliance/regulatory_policy_mapper.py` | 动作 × 辖区 → ENFORCE |
| 监管画像 | `src/maref/compliance/jurisdiction_profile.py` | OBSERVE / ADVISORY / ENFORCE |
| 监管场景测试 | `tests/compliance/test_regulatory_scenarios.py` | jurisdiction 参数未进入核心裁决 |
| 模型适配器 | `src/maref/execution/adapters/base.py:7` | 仅 `complete()` 等最小接口 |
| 本地适配器 | `src/maref/execution/adapters/local_adapter.py:10` | transformers 本地推理 |
| 分散 LLM 调用 | `src/maref/integration/feature_dev/llm_client.py:22` | OpenAI 兼容直连 |
| 技能执行器 | `src/maref/recursive/skill_executor.py:117` | 直接创建 provider client |
| Marketplace 门禁 | `src/maref/marketplace/registry.py` | 静态扫描启发式、沙箱模拟 |
| Harness | `src/maref/execution/harness/base.py:8` | `BaseHarness` |
| Loop | `src/maref/loop/base.py` | `LoopBase` / `GovernedLoop` |
| 工具注册 | `src/maref/tools/unified_registry.py` | MCP/Harness/Function 适配 |

---

## 8. 待核验清单

在对外发布或进入版本规划前，需要补齐：

- [ ] DSpark 官方仓库、release note、license、维护状态。
- [ ] 60%–85% 提速的硬件、模型、batch、序列长度、draft 模型配置。
- [ ] `DSparWrapper` 与 vLLM 版本兼容矩阵。
- [ ] dsh 当前版本、插件 API 稳定性、是否承诺向后兼容。
- [ ] dsh 的 sandbox/session log 是否有可复用规范。
- [ ] 地缘包法规引用的最新生效日期与修订状态。
- [ ] 外部政策包的签名/分发机制是否需要与现有供应链安全体系对齐。

---

## 9. 最终结论

DSpark 是**成本与延迟工具**，dsh 是**运行时设计参考**，二者都不应改变 MAREF 的治理核心。真正值得投入的是：

> **把地缘/行业政策做成可审计、可版本化、只能升级限制的声明式插件包，并接入现有治理主路径。**

这是一次中等规模的策略层改造，不是大规模重写。先做政策包，后做场景包，最后才考虑 dsh 式运行时插件化。
