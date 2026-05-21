# MAREF v0.25.0 实施计划 - 多Agent安全体系完善与协议标准化

**版本**: v0.25.0-rc
**创建日期**: 2026-05-13
**目标**: 完善多Agent安全体系 + 支持MCP/A2A协议 + 构建分布式信任机制

---

## 一、方案分析总结

### 1.1 方案三大战线

| 战线 | 任务数 | 周期 | 优先级 |
|------|--------|------|--------|
| S: 多Agent安全体系完善 | S1-S12 (12项) | 6周 | P0 |
| P: 协议标准化 | P1-P8 (8项) | 4周 | P0 |
| T: 分布式信任管理 | T1-T6 (6项) | 5周 | P1 |

### 1.2 现有模块评估

| 模块 | 当前状态 | v0.25目标 |
|------|----------|-----------|
| `mcp_security.py` | 基础工具阻止 (78行) | 完整安全门 + ATP集成 |
| `mcp_bridge.py` | 基础连接 | MCP Server/Client |
| `a2a_bridge.py` | 基础实现 | A2A完整协议支持 |
| 信任模块 | **缺失** | 从头构建 |
| 委托链 | **缺失** | 从头构建 |

### 1.3 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| ATP协议不稳定 | 集成可能需适配 | 设计适配器层 |
| MCP/A2A竞争 | 生态分裂 | 双协议+桥接 |
| 信任模型过复杂 | 难以验证 | 分阶段实现 |

---

## 二、实施阶段规划

### Phase 1: 信任链基础设施 (Week 1-2) 🔄

**目标**: 构建委托链追踪系统 + 信任边界标记

#### S1: 委托链追踪机制 ✅
- [x] **S1.1** 设计 `DelegationChain` 数据结构
  - `chain_id`: UUIDv7
  - `root_agent_id`: 根Agent标识
  - `depth`: 当前深度
  - `max_depth`: 最大委托深度(5)
  - `nodes`: 调用链节点列表
- [x] **S1.2** 实现 `DelegationChain` 核心方法
  - `create(root_agent_id) -> DelegationChain`
  - `add_delegation(parent_id, child_id, capability) -> bool`
  - `validate() -> ValidationResult`
- [x] **S1.3** 集成到Orchestration层
- [x] **S1.4** 单元测试 (10个场景)

**交付**: `src/maref/security/trust_chain/` ✅

#### S2: 信任边界标记 ✅
- [x] **S2.1** 定义 `TrustDomain` 类
  - `domain_id`: 域标识
  - `agents`: Agent集合
  - `policy`: 信任策略
- [x] **S2.2** 实现跨域调用检测
- [x] **S2.3** 生成边界报告

**交付**: `src/maref/security/trust_boundary/` ✅

#### S3: 零信任网关 ✅
- [x] **S3.1** 增强现有 `MCPSecurityGate`
  - 每次通信独立授权
  - 支持delegation limit
- [x] **S3.2** 速率限制实现
- [x] **S3.3** 审计日志增强

**交付**: 增强 `mcp_security.py` ✅

#### S4: ATP协议适配器 (Week 2)
- [x] **S4.1** 研究Lyrie.ai ATP规范
- [x] **S4.2** 设计ATP Client接口
- [x] **S4.3** 实现身份验证流程

**交付**: `src/maref/security/agent_identity/` ✅

---

### Phase 2: 跨Agent威胁防御 (Week 2-3)

#### S5: 共享状态污染检测 ✅
- [x] **S5.1** 定义共享状态监控接口 (SharedStateMonitor)
- [x] **S5.2** 实现异常模式检测
  - 突变率检测 (delta_ratio > threshold)
  - 频率异常检测 (burst mutations)
- [x] **S5.3** 隔离机制 (quarantine/unquarantine)

**交付**: `src/maref/security/state_monitor.py` ✅ (5 tests)

#### S6: 消息传递安全扫描 ✅
- [x] **S6.1** 增强消息安全扫描
  - Prompt injection模式识别
  - 风险评分 (0-100)
- [x] **S6.2** 风险分级 (LOW/MEDIUM/HIGH/CRITICAL)

**交付**: `src/maref/security/message_security.py` ✅ (4 tests)

#### S7: Emergent Behavior监控 ✅
- [x] **S7.1** 行为基线建模 (BehaviorBaseline)
- [x] **S7.2** 异常检测引擎 (3-sigma rule)
- [x] **S7.3** 多Agent交互风险评估 (emergent behavior detection)

**交付**: `src/maref/security/behavior_monitor.py` ✅ (4 tests)

#### S8: 拜占庭Agent隔离增强 ✅
- [x] **S8.1** 扩展Cross-Validator (ByzantineIsolationEnhancer)
- [x] **S8.2** 多维度异常判定 (vote inconsistency, weight anomaly, temporal pattern)
- [x] **S8.3** 节点恢复机制 (cold-start weight)

**交付**: `src/maref/security/byzantine_enhancer.py` ✅ (3 tests)

---

### Phase 3: 协议标准化 (Week 3-5)

#### P1: MCP Server实现
- [x] **P1.1** Tools端点
- [x] **P1.2** Resources端点
- [x] **P1.3** Prompts端点

**交付**: `src/maref/integration/mcp_server.py` ✅

#### P2: MCP Client集成 ✅ (v0.24 已有)
- [x] **P2.1** 外部MCP服务调用
- [x] **P2.2** 连接池管理
- [x] **P2.3** 错误处理标准化

#### P3: MCP安全加固
- [x] **P3.1** 协议级输入验证
- [x] **P3.2** 速率限制
- [x] **P3.3** 日志审计

**交付**: `src/maref/integration/mcp_security_middleware.py` ✅

#### P4: A2A Agent Card ✅ (v0.24 已有)
- [x] **P4.1** 符合规范的自我描述
- [x] **P4.2** 能力声明

#### P5: A2A消息协议 ✅ (v0.24 已有)
- [x] **P5.1** Task协议
- [x] **P5.2** Agent发现
- [x] **P5.3** 状态同步

#### P6: A2A安全传输
- [x] **P6.1** mTLS加密
- [x] **P6.2** 身份验证

**交付**: `src/maref/integration/a2a_secure_transport.py` ✅

#### P7: MCP↔A2A桥接 (Week 5)
- [x] **P7.1** 协议转换中间件
- [x] **P7.2** 状态映射

**交付**: `src/maref/integration/protocol_bridge.py` ✅

#### P8: 生态互操作验证
- [x] **P8.1** LangChain互操作测试
- [x] **P8.2** AutoGen互操作测试

**交付**: `tests/integration/test_ecosystem_interop.py` ✅

---

### Phase 4: 分布式信任管理 (Week 4-5) ✅

#### T1: 信任模型设计 ✅
- [x] **T1.1** 基于行为证据的信任分数模型
- [x] **T1.2** 信任传播算法

#### T2: 信任传播实现 ✅
- [x] **T2.1** 跨Agent信任关系图谱
- [x] **T2.2** 信任传播算法（带衰减迭代）

**交付**: `src/maref/security/trust_graph.py`

#### T3: 加权共识引擎 ✅
- [x] **T3.1** 实现公式 `W_agent = 1/|N_i| * Σ T_ij`
- [x] **T3.2** 动态权重更新 + 拜占庭惩罚

**交付**: `src/maref/security/weighted_consensus.py`

#### T4: 信任API ✅
- [x] **T4.1** `trust_score(agent_id)`
- [x] **T4.2** `get_trust_history(agent_id)`
- [x] **T4.3** `set_trust(agent_id, score)`

**交付**: `src/maref/security/trust_api.py`

#### T5: ATP集成 ✅
- [x] **T5.1** 与外部ATP服务互操作
- [x] **T5.2** 身份注册与验证

#### T6: 信任可视化 ✅
- [x] **T6.1** 信任图谱可视化（Cytoscape.js 兼容）
- [x] **T6.2** 实时状态摘要

**交付**: `src/maref/security/trust_visualization.py`

---

### Phase 5: 合规与审计 (Week 5-6) ✅

#### S9: Five Eyes合规基线 ✅
- [x] **S9.1** CISA/NSA六国联合安全指南映射
- [x] **S9.2** Agent身份管理
- [x] **S9.3** 通信安全增强

**交付**: `src/maref/compliance/five_eyes.py` (14项控制项映射)

#### S10: EU AI Act映射 ✅
- [x] **S10.1** 高风险系统合规清单
- [x] **S10.2** 人类监管系统设计

**交付**: `src/maref/compliance/eu_ai_act.py`

#### S11: 审计日志增强 ✅
- [x] **S11.1** 不可变日志导出 (Syslog/JSON)
- [x] **S11.2** 完整审计追踪

**交付**: `src/maref/governance/audit.py` 增强 (新增 export_syslog/export_json/get_audit_trail)

#### S12: 安全仪表板 ✅
- [x] **S12.1** 实时信任分数展示
- [x] **S12.2** 威胁检测面板
- [x] **S12.3** 合规状态可视化

**交付**: `src/maref/monitoring/safety_dashboard.py`

---

### Phase 6: 集成验证与自举 (Week 7-8) ✅

#### 集成测试
- [x] EIVL + Trust Chain联合测试
- [x] Cross-Validator + 加权共识联合测试
- [x] MCP/A2A协议兼容性测试

**交付**: `tests/integration/test_phase6_integration.py` (12 集成测试)

#### 自举验证
- [x] 安全模块链完整性自验证
- [x] 威胁检测→仪表板全流程

---

## 三、里程碑

| Week | 交付 | 状态 |
|------|------|------|
| Week 1 | S1-S2: 委托链追踪 + 信任边界 | ✅ |
| Week 2 | S3-S4: 零信任网关 + ATP适配器 | ✅ |
| Week 3 | S5-S8: 威胁防御模块 | ✅ |
| Week 4 | P1-P4: MCP Server + A2A基础 | ✅ |
| Week 5 | P5-P8 + T1-T2: 协议桥接 + 信任基础 | ✅ |
| Week 6 | T3-T6: 信任系统完整 | ✅ |
| Week 7 | S9-S12: 合规与仪表板 | ✅ |
| Week 8 | 集成测试 + 自举验证 | ✅ |

---

## 四、关键指标

| 指标 | 目标 |
|------|------|
| 安全模块测试覆盖 | ≥95% |
| 威胁检测能力 | 12类 |
| 协议支持 | MCP + A2A |
| 单元测试覆盖率 | >80% |
| Trust Escalation拦截率 | 100% |
| Cross-Agent Poisoning检测率 | >95% |

---

## 五、技术债务清理

- [ ] 全量代码零any类型 (Phase 6)
- [ ] 重复代码重构 (重复率<2%)

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| ATP协议不稳定 | 设计适配器层，解耦依赖 |
| MCP/A2A协议竞争 | 双协议支持+桥接 |
| 信任模型过于复杂 | 从简化模型开始 |
| 安全与性能权衡 | 异步处理 + 缓存优化 |

---

**最后更新**: 2026-05-15