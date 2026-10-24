# 宪法v1.6详细执行实施方案

> **方案编号**: CONSTITUTION-v1.6-EXEC-2026-09-14-001
> **方案日期**: 2026-09-14
> **方案状态**: ✅ 已批准
> **执行方**: MAREF Orchestrator

---

## 一、执行概览

### 1.1 执行目标
将宪法从v1.5升级到v1.6，同步L2验收新增的RL-006/007红线和CD-001~004跨维度不变量。

### 1.2 执行范围
1. 宪法第三条扩展（RL-006/007）
2. 宪法第八条扩展（跨维度形式化验证）
3. Changelog更新（v1.6）
4. TLA+验证确认
5. 相关文档更新

### 1.3 执行时间
- **开始时间**: 2026-09-14 14:00
- **预计完成**: 2026-09-14 16:00
- **实际完成**: 待确认

---

## 二、详细执行步骤

### 步骤1：准备宪法文件修改内容（14:00-14:30）

#### 1.1 修改文件头
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
```markdown
# Athena 系统宪法 v1.5
```
改为：
```markdown
# Athena 系统宪法 v1.6
```

#### 1.2 修改生效日期
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
```markdown
> **生效日期**: 2026-05-18
```
改为：
```markdown
> **生效日期**: 2026-09-14
```

#### 1.3 修改宪法第三条标题
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
```markdown
## 第三条 宪法红线（RL-001 ~ RL-005）
```
改为：
```markdown
## 第三条 宪法红线（RL-001 ~ RL-007）
```

#### 1.4 新增RL-006/007红线
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
在RL-005后新增：
```markdown
| **RL-006** | 跨维度改进不得修改安全相关维度权重 | $\square(d \in ProtectedDim \implies weight[d] = 50)$ | `CrossDimSecurityInv` |
| **RL-007** | 单轮跨维度改进不得超过3个目标文件 | $\square(fileModCount \leq 3)$ | `MaxFilesPerRoundInv` |
```

#### 1.5 修改宪法第八条
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
在第八条末尾新增：
```markdown
### 8.1 跨维度形式化验证

跨维度改进（Cross-dimension improvement）须满足以下形式化不变量：
- **CD-INV-001**: 安全相关维度权重不可变（ProtectedDim weights = 50）
- **CD-INV-002**: 单轮改进文件数不超过3（fileModCount ≤ 3）
- **CD-INV-003**: 跨影响监控必须始终激活（crossImpactMonitored = TRUE）
- **CD-INV-004**: 权重调整量不超过阈值（weightAdjustmentTotal ≤ 0.15）

验证文件: `src/formal/MAREF_ConstitutionalRedLines.tla`
```

#### 1.6 更新Changelog
**文件**: `docs/CONSTITUTION.md`
**修改内容**:
```markdown
| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.5 | 2026-05-18 | 当前生效版本。确立 5 条宪法红线、TLA+ 形式化验证、HITL 四级审批、跨仓库治理（Athena / SkillOS / openclaw 等平级生态不得作为 MAREF 上位法）。 |
```
改为：
```markdown
| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.6 | 2026-09-14 | 宪法红线扩展至7条（RL-006/007：跨维度安全保护），新增跨维度形式化验证（CD-INV-001~004），同步L2验收新增内容。 |
| v1.5 | 2026-05-18 | 当前生效版本。确立 5 条宪法红线、TLA+ 形式化验证、HITL 四级审批、跨仓库治理（Athena / SkillOS / openclaw 等平级生态不得作为 MAREF 上位法）。 |
```

---

### 步骤2：执行宪法文件修改（14:30-15:00）

#### 2.1 修改宪法文件
**执行命令**: 使用Edit工具修改`docs/CONSTITUTION.md`

#### 2.2 验证修改内容
**检查项**:
- [ ] 文件头版本号已更新
- [ ] 生效日期已更新
- [ ] 第三条标题已更新
- [ ] RL-006/007已添加
- [ ] 第八条扩展已添加
- [ ] Changelog已更新

---

### 步骤3：TLA+验证确认（15:00-15:30）

#### 3.1 验证现有不变量
**执行命令**:
```bash
cd src/formal && java -cp tla2tools.jar tlc2.TLC \
  -config MAREF_ConstitutionalRedLinesMC.cfg \
  MAREF_ConstitutionalRedLines
```

**验证目标**: INV-001~005全部通过

#### 3.2 验证跨维度不变量
**执行命令**:
```bash
cd src/formal && java -cp tla2tools.jar tlc2.TLC \
  -config MAREF_CrossDimensionalMC.cfg \
  MAREF_CrossDimensional
```

**验证目标**: CD-INV-001~004全部通过

#### 3.3 验证RSI红线不变量
**执行命令**:
```bash
cd src/formal && java -cp tla2tools.jar tlc2.TLC \
  -config MAREF_RSIRedlinesMC.cfg \
  MAREF_RSIRedlines
```

**验证目标**: RSIRL001~007全部通过

#### 3.4 验证结果记录
**记录文件**: `docs/CONSTITUTIONv1.6-TLA-validation-results.md`

---

### 步骤4：更新相关文档引用（15:30-16:00）

#### 4.1 更新AGENTS.md
**文件**: `AGENTS.md`
**修改内容**:
- 更新宪法版本引用（v1.5 → v1.6）
- 更新宪法红线数量（5条 → 7条）

#### 4.2 更新oss-execution-norm-v1.0.md
**文件**: `docs/oss-execution-norm-v1.0.md`
**修改内容**:
- 更新宪法版本引用（v1.5 → v1.6）

#### 4.3 更新release-gate.md
**文件**: `docs/release-gate.md`
**修改内容**:
- 更新宪法版本引用（v1.5 → v1.6）

#### 4.4 更新相关代码注释
**文件**: `src/maref/recursive/meta_agent_closure.py`
**修改内容**:
- 更新宪法版本引用（v1.5 → v1.6）

---

## 三、执行检查清单

### 3.1 修改前检查
- [ ] 已阅读审计报告（docs/CONSTITUTIONAudit.md）
- [ ] 已阅读修订建议（docs/CONSTITUTIONv1.6-proposal.md）
- [ ] 已确认TLA+验证通过（docs/CONSTITUTIONv1.6-TLA-validation.md）
- [ ] 已确认宪法委员会审议通过（docs/CONSTITUTION-COMMITTEE-2026-09-14.md）
- [ ] 已确认HITL四级审批通过（docs/HITL-CONSTITUTION-v1.6-approval.md）

### 3.2 修改中检查
- [ ] 文件头版本号已更新
- [ ] 生效日期已更新
- [ ] 第三条标题已更新
- [ ] RL-006/007已添加
- [ ] 第八条扩展已添加
- [ ] Changelog已更新

### 3.3 修改后检查
- [ ] TLA+验证通过
- [ ] AGENTS.md已更新
- [ ] oss-execution-norm-v1.0.md已更新
- [ ] release-gate.md已更新
- [ ] 相关代码注释已更新

---

## 四、风险控制

### 4.1 执行风险
1. **文件修改失败**: 准备回滚方案
2. **TLA+验证失败**: 准备问题排查方案
3. **文档更新遗漏**: 准备完整性检查方案

### 4.2 回滚方案
1. **宪法文件回滚**: 恢复到v1.5版本
2. **文档引用回滚**: 恢复到v1.5引用
3. **TLA+验证回滚**: 重新验证v1.5不变量

### 4.3 应急联系
- **执行方**: MAREF Orchestrator
- **审批方**: MAREF Governance Audit
- **监督方**: Athena 系统宪法委员会

---

## 五、执行记录

### 5.1 执行日志
**日志文件**: `docs/CONSTITUTION-v1.6-execution-log.md`

### 5.2 执行签名
**执行人**: ____________________
**执行时间**: ____________________
**执行结果**: ____________________

---

**方案制定方**: MAREF Governance Audit
**方案依据**: 宪法第十二条
**下一步**: 执行宪法v1.6修订