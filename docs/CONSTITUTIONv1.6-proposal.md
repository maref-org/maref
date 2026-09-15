# Athena 系统宪法 v1.6 迭代建议

> **基于审计报告**: docs/CONSTITUTIONAudit.md
> **建议版本**: v1.6
> **建议日期**: 2026-09-14
> **状态**: 待宪法委员会审议

---

## 一、迭代原则

1. **向后兼容**: 不削弱现有RL-001~005任何一条
2. **形式化同步**: 所有新增红线必须TLA+验证
3. **最小变更**: 仅填补缺口，不重构现有条款
4. **执行可行**: 新增条款必须有对应代码实现

---

## 二、具体修订建议

### 修订1：宪法第三条扩展（RL-006/007）

**当前内容**:
```
| 编号 | 红线 | TLA+ 不变量 | 适用范围 |
|------|------|-------------|---------|
| **RL-001** | 智能体不得修改自身安全红线 | $\square(rl.modified\_by \notin Agents)$ | `RedLineImmutability` |
| **RL-002** | 智能体不得禁用或绕过安全门 | $\square(SafetyGate.active = True)$ | `SafetyGateIntegrity` |
| **RL-003** | 智能体不得在无审计追踪的情况下执行代码 | $\square(s.trace\_ctx \neq \emptyset \lor s.live = False)$ | `AuditTrailCompleteness` |
| **RL-004** | 智能体不得在未经宪法审查的情况下克隆自身 | $\square(clone \implies human\_reviewed)$ | `ConstitutionSupremacy` |
| **RL-005** | 智能体不得单方面修改信任评估权重 | $\square(trust\_weight \implies consensus)$ | `HumanConstitutionSoleAuthority` |
```

**建议修订**:
```
| 编号 | 红线 | TLA+ 不变量 | 适用范围 |
|------|------|-------------|---------|
| **RL-001** | 智能体不得修改自身安全红线 | $\square(rl.modified\_by \notin Agents)$ | `RedLineImmutability` |
| **RL-002** | 智能体不得禁用或绕过安全门 | $\square(SafetyGate.active = True)$ | `SafetyGateIntegrity` |
| **RL-003** | 智能体不得在无审计追踪的情况下执行代码 | $\square(s.trace\_ctx \neq \emptyset \lor s.live = False)$ | `AuditTrailCompleteness` |
| **RL-004** | 智能体不得在未经宪法审查的情况下克隆自身 | $\square(clone \implies human\_reviewed)$ | `ConstitutionSupremacy` |
| **RL-005** | 智能体不得单方面修改信任评估权重 | $\square(trust\_weight \implies consensus)$ | `HumanConstitutionSoleAuthority` |
| **RL-006** | 跨维度改进不得修改安全相关维度权重 | $\square(d \in ProtectedDim \implies weight[d] = 50)$ | `CrossDimSecurityInv` |
| **RL-007** | 单轮跨维度改进不得超过3个目标文件 | $\square(fileModCount \leq 3)$ | `MaxFilesPerRoundInv` |
```

**依据**:
- `configs/rsi_redlines.yaml` 已定义RL-006/007
- `src/maref/evolution/constitution_guard.py` 已实现
- `src/formal/MAREF_ConstitutionalRedLines.tla` CD-INV-001/002已验证

### 修订2：宪法第八条扩展（跨维度形式化验证）

**当前内容**:
```
## 第八条 形式化验证前置

涉及治理状态机、宪法红线、安全门的关键性质须 TLA+ 模型检验通过后方可实现。MAREF 采用 34 态 Gray Code FSM（10 治理 + 24 Agent，Hamming 距离 = 1 转换）保证稳定性。
```

**建议修订**:
```
## 第八条 形式化验证前置

涉及治理状态机、宪法红线、安全门的关键性质须 TLA+ 模型检验通过后方可实现。MAREF 采用 34 态 Gray Code FSM（10 治理 + 24 Agent，Hamming 距离 = 1 转换）保证稳定性。

### 8.1 跨维度形式化验证

跨维度改进（Cross-dimension improvement）须满足以下形式化不变量：
- **CD-INV-001**: 安全相关维度权重不可变（ProtectedDim weights = 50）
- **CD-INV-002**: 单轮改进文件数不超过3（fileModCount ≤ 3）
- **CD-INV-003**: 跨影响监控必须始终激活（crossImpactMonitored = TRUE）
- **CD-INV-004**: 权重调整量不超过阈值（weightAdjustmentTotal ≤ 0.15）

验证文件: `src/formal/MAREF_ConstitutionalRedLines.tla`
```

### 修订3：宪法第十条细化（外部Agent决策边界）

**当前内容**:
```
## 第十条 外部 Code Agent 治理

凡由 Claude Code / OpenCode / Trae CN 等外部 Code Agent 在本仓库执行的操作：

1. 启动前必须阅读 AGENTS.md（宪法红线）；
2. 操作过程受 GaaS（Governance-as-a-Service）钩子与 sidecar 观察；
3. 高危操作须经 HITL 确认；
4. 不得引入与上位法冲突的外部规范作为本仓库治理依据；
5. 不得修改受 Orchestrator 保护的文件（见 AGENTS.md "Boundaries"）。
```

**建议修订**:
```
## 第十条 外部 Code Agent 治理

凡由 Claude Code / OpenCode / Trae CN 等外部 Code Agent 在本仓库执行的操作：

1. 启动前必须阅读 AGENTS.md（宪法红线）；
2. 操作过程受 GaaS（Governance-as-a-Service）钩子与 sidecar 观察；
3. 高危操作须经 HITL 确认；
4. 不得引入与上位法冲突的外部规范作为本仓库治理依据；
5. 不得修改受 Orchestrator 保护的文件（见 AGENTS.md "Boundaries"）。

### 10.1 外部Agent决策边界

外部Agent的自主决策必须满足：
- **决策范围**: 仅限技术实现决策，不得涉及治理决策
- **克隆限制**: Agent克隆须经宪法审查（RL-004）
- **跨域限制**: 跨域调用须通过TrustBoundaryManager授权
- **审计要求**: 所有决策必须有审计追踪（RL-003）

### 10.2 Agent自主决策宪法限制

Agent自主决策不得：
- 修改宪法红线（RL-001）
- 禁用安全门（RL-002）
- 跳过审计追踪（RL-003）
- 单方面克隆自身（RL-004）
- 修改信任权重（RL-005）
- 修改安全维度权重（RL-006）
- 超过文件限制（RL-007）
```

---

## 三、新增条款建议

### 新增条款：递归自演进稳定性（第七条扩展）

**建议内容**:
```
## 第七条 递归自演进约束

递归自演进引擎在 Lyapunov 稳定性条件下须证明收敛；自演进不得削弱宪法红线不得降低安全级别；免疫系统须运行 SAEB 于自身以检测基因退化。

### 7.1 递归自演进稳定性要求

递归自演进必须满足：
- **Lyapunov收敛证明**: 每次自演进须证明Lyapunov函数单调递减
- **基因退化检测**: 免疫系统须定期运行SAEB自检
- **稳定性阈值**: Lyapunov指数必须小于0（收敛条件）
- **退化熔断**: 基因退化超过阈值须触发熔断

### 7.2 递归自演进形式化验证

递归自演进的关键性质须TLA+验证：
- **收敛性**: 自演进序列必须收敛到稳定状态
- **安全性**: 自演进不得削弱宪法红线
- **完整性**: 自演进必须有完整审计追踪
```

### 新增条款：数据跨境流动（第九条扩展）

**建议内容**:
```
## 第九条 数据主权与合规

敏感数据不出境；国密标准（SM2 / SM3 / SM4-GCM）为默认加密基线；GDPR / 等保 2.0 / 网络安全法 / SOC2 合规门禁不可降级。

### 9.1 跨境数据流动治理

跨境数据流动必须满足：
- **数据分类**: 敏感数据不得出境（包括用户数据、治理数据）
- **出境审批**: 跨境数据须经HITL四级审批
- **加密要求**: 跨境数据须使用国密标准加密
- **审计追踪**: 跨境数据必须有完整审计记录

### 9.2 国密标准实现

国密标准（SM2/SM3/SM4-GCM）为默认加密基线：
- **SM2**: 非对称加密（用于数字签名）
- **SM3**: 哈希算法（用于完整性校验）
- **SM4-GCM**: 对称加密（用于数据加密）
```

---

## 四、TLA+验证要求

### 4.1 现有不变量保持

必须保持以下不变量验证通过：
- **INV-001~005**: 宪法红线不变量
- **CD-INV-001~004**: 跨维度不变量
- **RSI-RL-001~007**: RSI红线不变量

### 4.2 新增不变量验证

新增条款须TLA+验证：
- **递归自演进稳定性不变量**: Lyapunov收敛性
- **跨境数据流动不变量**: 数据不出境

### 4.3 验证命令

```bash
# 验证现有不变量
cd src/formal && java -cp tla2tools.jar tlc2.TLC \
  -config MAREF_ConstitutionalRedLinesMC.cfg \
  MAREF_ConstitutionalRedLines

# 验证跨维度不变量
cd src/formal && java -cp tla2tools.jar tlc2.TLC \
  -config MAREF_CrossDimensionalMC.cfg \
  MAREF_CrossDimensional
```

---

## 五、实施计划

### 阶段1：立即修订（v1.6）
1. **宪法第三条扩展**: 新增RL-006/007红线
2. **宪法第八条扩展**: 新增跨维度形式化验证要求
3. **宪法第十条细化**: 明确外部Agent决策边界

### 阶段2：中期迭代（v1.7）
1. **第七条扩展**: 新增递归自演进稳定性要求
2. **第九条扩展**: 新增跨境数据流动治理

### 阶段3：长期迭代（v2.0）
1. **宪法结构重组**: 按治理域重新组织条款
2. **形式化验证全覆盖**: 所有治理性质必须TLA+验证

---

## 六、风险控制

### 修订风险
1. **向后兼容性**: 所有新增条款不削弱现有红线
2. **形式化验证**: 所有新增条款必须TLA+验证
3. **执行可行性**: 新增条款必须有对应代码实现

### 回滚机制
1. **版本控制**: 宪法修订必须有版本号
2. **变更记录**: 所有修订必须记录在changelog
3. **回滚路径**: 宪法修订必须有回滚路径

---

## 七、结论

**宪法v1.6修订建议已准备就绪**。核心修订：
1. 宪法第三条扩展RL-006/007
2. 宪法第八条扩展跨维度形式化验证
3. 宪法第十条细化外部Agent决策边界

**建议立即启动宪法委员会审议**，优先解决宪法文本与形式化验证脱节问题。

---

**建议方**: MAREF Governance Audit
**依据**: docs/CONSTITUTIONAudit.md
**下一步**: 提交宪法委员会审议