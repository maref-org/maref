# MAREF v0.25.0 安全体系增强实施计划

**版本**: v0.25.0-rc  
**创建日期**: 2026-05-13  
**目标**: 基于2026年多Agent安全体系技术研究报告，完成安全模块从原型到生产级的演进  

---

## 一、背景分析

### 1.1 威胁态势

- **Five Eyes Agentic AI安全指南** (2026-05-01): 多Agent编排系统攻击面已达国家基础设施级别
- **NIST RFI反馈**: 识别Trust Escalation、Cross-Agent Poisoning、Emergent Shadow Behavior等新型威胁
- **CSA Mythos-Ready研究**: 攻击能力加速，AI主导攻击在8分钟内可获管理员权限

### 1.2 MAREF现有模块评估

| 模块 | 能力 | 不足 |
|------|------|------|
| EIVL-WASM-Sandbox | 物理隔离、WASM沙箱、Merkl Tree存证 | 未覆盖Agent身份验证、未支持ATP协议 |
| Cross-Validator | AST归一化、共识聚类、行为异常检测 | 未支持MCP/A2A、未追踪委托链 |
| Reputation System | 信誉分动态调整 | 集中式架构、未实现分布式信任 |

---

## 二、核心目标

1. **安全体系升级**: 从单一验证到完整信任链管理
2. **协议标准化**: 支持MCP/A2A实现生态互操作
3. **分布式信任**: 从集中式信誉到去中心化信任传播
4. **合规准备**: 满足Five Eyes和EU AI Act要求

---

## 三、迭代规划

### Phase 1: 信任链安全管理 (Week 1-2)

#### 3.1.1 委托链追踪系统

**目标**: 防止信任升级攻击

**实现**:
- 为每次Agent调用生成唯一ID (UUIDv7)
- 记录完整调用链: `parent_agent_id -> child_agent_id -> action`
- 委托链数据结构:

```python
@dataclass
class DelegationChain:
    chain_id: str          # UUID
    root_agent_id: str
    depth: int            # 当前深度
    max_depth: int = 5    # 最大委托深度
    nodes: List[ChainNode]
    created_at: datetime
```

**关键方法**:
- `DelegationChain.create(root_agent_id) -> DelegationChain`
- `DelegationChain.add_delegation(parent_id, child_id, capability) -> bool`
- `DelegationChain.validate() -> ValidationResult`

#### 3.1.2 信任边界标记

**目标**: 跨信任域调用强制重新验证

**实现**:
- 信任域定义: Agent分组 + 信任策略
- 边界检查: 跨域调用触发二次验证
- 审计报告生成

### Phase 2: 跨Agent威胁防御 (Week 2-3)

#### 3.2.1 共享状态污染检测

**目标**: 检测Agent共享变量修改异常

**实现**:
- 监控共享状态读写操作
- 异常模式检测: 突变率、频率异常
- 隔离机制: 污染Agent自动隔离

#### 3.2.2 消息传递安全扫描

**目标**: 防止prompt injection跨Agent传播

**实现**:
- 消息内容扫描: 注入模式识别
- 上下文隔离: 敏感信息过滤
- 风险评分: 0-100分级

#### 3.2.3 Emergent Behavior监控

**目标**: 检测Agent交互产生的未预期危险行为

**实现**:
- 行为基线学习: 正常行为模式建模
- 异常检测: 偏离基线时告警
- 组合分析: 多Agent交互风险评估

### Phase 3: 分布式信任管理 (Week 3-4)

#### 3.3.1 ATP集成

**目标**: 实现Agent身份验证

**实现**:
- Agent Trust Protocol (ATP) 客户端
- 公钥密码学身份证明
- 身份注册与验证流程

#### 3.3.2 加权共识机制

**目标**: 高信任Agent更大决策权重

**实现**:
- 信任权重计算: `W_agent = 1/|N_i| * Σ T_ij`
- 共识决策: softmax(总分)最高者
- 动态更新: 基于行为证据调整

#### 3.3.3 信任图谱构建

**目标**: 跨Agent信任关系可视化

**实现**:
- 图数据库存储: Agent关系
- 信任传播算法: 跨系统信任链
- 查询接口: 实时信任状态

### Phase 4: 协议标准化 (Week 4-5)

#### 3.4.1 MCP Server/Client

**目标**: 支持Model Context Protocol

**实现**:
- MCP Server: Tools/Resources端点
- MCP Client: 外部MCP服务调用
- 协议适配器: MAREF -> MCP转换

#### 3.4.2 A2A协议支持

**目标**: 支持Agent-to-Agent通信

**实现**:
- Agent Card: 符合规范的自我描述
- Task协议: 任务传递
- 发现协议: Agent发现
- 状态同步: 会话状态管理

#### 3.4.3 协议桥接

**目标**: MCP ↔ A2A互转

**实现**:
- 消息格式转换
- 状态映射
- 错误处理标准化

### Phase 5: 合规准备 (Week 5-6)

#### 3.5.1 Five Eyes合规基线

| 控制项 | 当前状态 | 改进目标 |
|--------|----------|----------|
| Agent身份管理 | 部分(仅信誉分) | 完整标识系统 |
| 通信安全 | 需加强 | 加密+来源验证 |
| 能力边界 | 已有 | 增强边界控制 |
| 审计日志 | 基础 | 完整不可变 |
| 人类监督 | 需实现 | 高风险人工批准 |

#### 3.5.2 EU AI Act准备

- 人类监管系统设计
- 透明度文档生成
- 风险管理流程实现

### Phase 6: 集成验证与自举 (Week 7-8)

#### 3.6.1 模块集成测试

- EIVL + Trust Chain 联合测试
- Cross-Validator + 加权共识 联合测试
- MCP/A2A 协议兼容性测试
- 端到端安全流程测试

#### 3.6.2 TLA+形式化验证

- Cross-Validator共识算法规范
- 委托链追踪状态机验证
- 加权共识数学性质证明

#### 3.6.3 技术债务清理

- 全量代码零any类型
- 重复代码重构

#### 3.6.4 自举验证

- 安全模块代码由MAREF自身生成
- 生成代码通过EIVL + Cross-Validator验证
- 人工审查关键逻辑

---

## 四、模块清单

### 4.1 新增模块

| 模块 | 路径 | 描述 |
|------|------|------|
| trust_chain | `src/maref/security/trust_chain/` | 委托链追踪系统 |
| agent_identity | `src/maref/security/agent_identity/` | ATP身份验证 |
| trust_graph | `src/maref/security/trust_graph/` | 分布式信任图谱 |
| protocol_bridge | `src/maref/security/protocol_bridge/` | MCP/A2A协议桥接 |

### 4.2 增强模块

| 模块 | 增强内容 |
|------|----------|
| EIVL-WASM-Sandbox | 集成ATP身份验证 |
| Cross-Validator | 添加MCP/A2A适配器、委托链追踪 |
| Reputation System | 分布式信任传播、加权共识 |

---

## 五、验收标准

1. 委托链追踪覆盖100%的Agent调用
2. 跨域调用100%经过二次验证
3. 污染检测准确率>95%
4. MCP Server/Client完整支持
5. A2A协议完整支持
6. Five Eyes合规基线100%覆盖
7. 单元测试覆盖率>80%
8. Trust Escalation攻击拦截率100%
9. Cross-Agent Poisoning攻击检测率>95%
10. 加权共识数学验证通过(TLC)
11. 全量代码零any类型(TypeScript strict)
12. 自举验证通过(MAREF生成代码通过自身质量门)

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| ATP协议兼容性 | 分阶段集成，先支持基础验证 |
| 性能影响 | 异步处理、缓存优化 |
| 协议碎片化 | 优先支持主流协议(MCP/A2A) |

---

## 七、现有模块集成

### 7.1 EIVL与信任链集成

- 委托链验证结果作为EIVL输入的前置条件
- Merkle Tree扩展：加入委托链哈希
- 验证节点与Agent节点物理隔离（现有设计保留）

### 7.2 Cross-Validator与加权共识

- 共识算法升级：从多数投票 → 加权投票
- 行为基线与emergent behavior监控联动
- AST归一化增强：支持MCP/A2A协议输出解析

### 7.3 Deterministic Router安全增强

- 安全任务(SECURITY_AUDIT)强制进入深度验证流程
- 任务复杂度评估加入威胁维度
- 跨信任域调用自动触发边界检查

### 7.4 Reputation System与信任图谱

- 信誉分与信任权重计算统一
- 分布式信任传播算法集成
- 冻结Agent自动加入隔离名单

### 7.5 SPARC工作流安全嵌入

| 阶段 | 安全嵌入点 |
|------|------------|
| Spec | 威胁建模检查 |
| Plan | 能力边界验证 |
| Action | 实时行为监控 |
| Review | EIVL签批 + 人工批准 |
| Close | 审计日志归档 |

---

## 八、Layer 1-4 信任模型强化

### 8.1 Layer 1: 最小信任假设（持续）

- Merkle Tree存证扩展至委托链
- WASM沙箱增强：新增系统调用白名单
- 委托链哈希作为额外验证维度

### 8.2 Layer 2: 形式化验证（新增）

- Cross-Validator共识算法TLA+规范
- TLC模型检查：4 Agent、1 拜占庭节点场景
- 委托链追踪状态机TLA+验证

### 8.3 Layer 3: 红队测试扩展

| 新威胁场景 | 测试目标 | 验收标准 |
|-----------|----------|----------|
| Trust Escalation | 委托链深度>5时拦截 | 100% |
| Cross-Agent Poisoning | 共享状态污染检测 | 准确率>95% |
| Emergent Shadow Behavior | 组合行为异常检测 | 提前预警率>90% |
| ATP身份伪造 | 身份验证绕过拦截 | 100% |

### 8.4 Layer 4: 第三方审计

- 季度安全审计计划
- 开源社区代码审查
- 红队报告与漏洞修复公开

---

## 九、测试场景补充

### 9.1 新增测试场景

| 模块 | 测试场景 | 数量 | 说明 |
|------|---------|------|------|
| Trust Chain | 信任升级攻击模拟 | 2 | 委托链深度超限、跨域调用绕过 |
| Agent Identity | ATP身份伪造攻击 | 2 | 密钥伪造、重放攻击 |
| Cross-Validator | 加权共识正常/异常 | 3 | 高权重Agent作弊、权重失衡、权重串通 |
| Protocol Bridge | MCP↔A2A互转 | 2 | 格式丢失、状态不一致 |
| Emergent Behavior | 组合行为异常 | 2 | 多Agent协同偏离基线 |

### 9.2 回归测试

- EIVL 10项测试场景（知识库原定义）
- Cross-Validator 8项测试场景（知识库原定义）
- Ruflo #640 回归测试

---

## 十、技术债务清理

### 10.1 零Any类型专项（Phase 6）

- 审计当前代码库any类型数量
- 分优先级修复：安全模块 → 核心模块 → 辅助模块
- 验收：全量代码`npx tsc --noEmit` 0错误

### 10.2 重复代码重构（Phase 6）

- 检测重复率>3%的代码块
- 提取公共函数至shared模块
- 验收：重复率<2%

---

## 十一、自举验证计划

MAREF安全模块自身必须通过自身质量门：

1. **代码生成**：安全模块代码由MAREF自身生成
2. **EIVL验证**：生成的代码通过EIVL测试执行
3. **Cross-Validator验证**：生成的代码通过共识验证
4. **人工审查**：关键安全逻辑人工复核

---

## 十二、运维监控增强

| 指标 | 告警阈值 | 处理方式 |
|------|---------|---------|
| 委托链深度超限率 | >1% | 审查任务配置 |
| 跨域调用重验失败率 | >5% | 检查信任边界配置 |
| ATP验证延迟 | >200ms | 扩容验证节点 |
| 加权共识偏差 | >0.1 | 审查信任权重 |

---

**参考**:
- 2026年多Agent安全体系技术研究报告
- Five Eyes "Careful Adoption of Agentic AI Services" (2026-05-01)
- Lyrie.ai Agent Trust Protocol (ATP) (2026-05-11)
- MAREF工程文档完整版（2026-05-12）