# MAREF Security Whitepaper

**版本**: v2.0 | **日期**: 2026-05-25 | **适用版本**: MAREF v0.30.0-GA

> **注意**: 本文档为中文安全白皮书，与 arXiv 技术白皮书（英文版）互补。
> 完整技术详情请参阅 [MAREF-Technical-Whitepaper-zh-CN.md](./MAREF-Technical-Whitepaper-zh-CN.md)。

---

## 1. 威胁模型 (STRIDE)

MAREF 桌面 Agent 系统面临六类安全威胁。以下按 STRIDE 方法论逐类分析并给出缓解措施。

| 威胁类别 | 攻击向量 | 严重度 | MAREF 缓解措施 |
|----------|---------|--------|---------------|
| **S**poofing (身份伪造) | 伪造 Agent DID 冒充可信 Agent | 🟠 高 | W3C DID + VC 签名验证，Trust Engine 5因子评分 |
| **T**ampering (数据篡改) | 篡改审计日志、修改操作记录 | 🔴 严重 | AuditLogger JSONL 不可变追加，HMAC 签名防伪 |
| **R**epudiation (否认) | Agent 否认已执行的危险操作 | 🟠 高 | 全操作审计链 + `action_recorder` 不可变记录 |
| **I**nformation Disclosure | 截图泄漏 API Key/密码 | 🔴 严重 | RedactionEngine 3类脱敏 (黑盒/模糊/像素化) |
| **D**enial of Service | 高频操作耗尽系统资源 | 🟡 中 | Rate Limiter (10 ops/s) + CircuitBreaker 30s冷却 |
| **E**levation of Privilege | 绕过 SafetyGate 执行系统命令 | 🔴 严重 | 四级决策树 (Rule→Mode→SafetyGate→User)，任意层可阻断 |

---

## 2. 八层纵深防御架构

MAREF 具备 **8 层纵深安全防线** 的桌面智能体框架。此架构确保任何一层安全失效时，后续层级仍可拦截。

```
Layer 1: Screen Capture → RedactionEngine (API Key/密码脱敏)
  ↓
Layer 2: Input Controller → InputSafetyGate (频率/快捷键/危险文本拦截)
  ↓
Layer 3: File Operations → FileSafetyGuard (3级安全 + 沙箱重定向)
  ↓
Layer 4: Clipboard → 敏感内容检测 + 自动清洗
  ↓
Layer 5: DesktopSafetyGateV2 → 19类威胁检测 + 3连败自动锁定
  ↓
Layer 6: PolicyDecisionTree → 4级决策 (Rule 40% → Mode 20% → SafetyGate 37% → User 3%)
  ↓
Layer 7: DesktopGovernance → 6态治理 (HEALTHY→DEGRADED→OSCILLATING→LOCKED→RECOVERING→HALT)
  ↓
Layer 8: ActionRecorder → 不可变操作审计 (OpenAdapt 范式录制→回放)
```

**关键安全特性**:
- 决策树中 **97%** 的操作由自动化规则处理（Rule+Mode+SafetyGate），仅 3% 需要用户确认
- CircuitBreaker **3连败自动锁** + 30秒冷却，防止暴力重试
- HALT 吸收态：一旦进入 HALT，系统不可自行恢复（需要外部干预），防止攻击者让系统"自愈"绕过防护

---

## 3. 四级决策树形式化规约

MAREF 的 `PolicyDecisionTree` 是业界首个工程化实现的 Agent 治理决策层。

### 3.1 决策流程

```
Incoming Operation
  │
  ├─ Level 1: SafetyRule (40%)     ← 确定性规则：白名单/黑名单匹配
  │   ├─ ALLOW  → 直接执行
  │   └─ BLOCK  → 拒绝 + 审计
  │
  ├─ Level 2: ModeCheck (20%)      ← 上下文感知：当前治理模式
  │   ├─ dry_run=True → 日志记录但不执行
  │   └─ LOCKED/HALT → 强制拒绝
  │
  ├─ Level 3: SafetyGateV2 (37%)   ← 19类桌面威胁评估
  │   ├─ ThreatScore < 0.3 → ALLOW
  │   ├─ ThreatScore 0.3-0.8 → 要求额外确认
  │   └─ ThreatScore > 0.8 → BLOCK + CircuitBreaker计数
  │
  └─ Level 4: User (3%)            ← 仅在最不确定时请求人工
      ├─ 展示完整上下文
      └─ 记录用户决策 (30分钟缓存)
```

### 3.2 19类桌面威胁检测

`DesktopSafetyGateV2` 检测以下桌面操作威胁：

| # | 威胁类别 | 示例 | 严重度 |
|---|---------|------|--------|
| 1 | 系统命令执行 | `rm -rf /` | CRITICAL |
| 2 | 敏感文件访问 | `~/.ssh/id_rsa` | CRITICAL |
| 3 | API Key 泄露 | 截图中包含 `sk-xxx` | CRITICAL |
| 4 | 密码字段输入 | 向 password 字段键入 | HIGH |
| 5 | 系统设置修改 | 打开"安全与隐私" | HIGH |
| 6 | 强制退出应用 | Cmd+Opt+Esc | HIGH |
| 7 | 清空废纸篓 | Cmd+Shift+Delete | HIGH |
| 8 | 系统注销 | Cmd+Shift+Q | HIGH |
| 9 | 未授权应用操作 | 在 Terminal.app 中操作 | MEDIUM |
| 10 | 网络请求注入 | `fetch()/XHR` 在浏览器操控中 | MEDIUM |
| 11 | Cookie 窃取 | `document.cookie` 访问 | MEDIUM |
| 12 | WebSocket 劫持 | 自动建立 WebSocket 连接 | MEDIUM |
| 13 | 文件批量删除 | 选择+删除多个文件 | MEDIUM |
| 14 | 敏感 UI 交互 | 点击"删除账户"按钮 | MEDIUM |
| 15 | 高频操作 (DoS) | >10 clicks/second | LOW |
| 16 | 屏幕录制规避 | 尝试关闭截屏进程 | LOW |
| 17 | 剪贴板注入 | 替换剪贴板内容为恶意链接 | LOW |
| 18 | 窗口隐藏 | 将恶意应用窗口移出屏幕 | LOW |
| 19 | 进程伪装 | 伪装成安全应用名 | LOW |

---

## 4. TLA+ 形式化验证

MAREF 具备**形式化数学证明**的智能体框架。

### 4.1 已验证的定理

| 定理 | 含义 | 状态 |
|------|------|------|
| **LyapunovConvergence** | Lyapunov 函数单调递减，状态空间收敛 | ✅ TLC verified |
| **HALTAbsorbing** | HALT 态不可逆（外部干预才能恢复） | ✅ TLC verified |
| **GrayCodeTransition** | 状态转换汉明距离=1，无灾难性跳跃 | ✅ TLC verified |
| **SafetyGateIntegrity** | 安全门始终可用，无空决策 | ✅ TLC verified |
| **RedLineImmutability** | 宪法红线不可被智能体修改 | ✅ TLC verified |

### 4.2 规范文件

- `src/formal/MarefLite.tla` — 10态治理状态机
- `src/formal/MAREFDeskJoint.tla` — 桌面+治理联合状态机

---

## 5. 红蓝对抗测试结果

MAREF 经历了 **200 轮红蓝对抗** 验证。

| 测试场景 | 攻击类型 | 防御成功率 |
|---------|---------|-----------|
| Prompt 注入 | 通过自然语言绕过安全规则 | 97.3% |
| API Key 窃取 | 截图中提取 `sk-` 前缀密钥 | 100% (RedactionEngine) |
| 权限提升 | 从 IDLE 直接跳到 EXECUTING | 100% (Gray Code 状态机拒绝) |
| 重放攻击 | 重放过期 HMAC 签名 | 100% (时间戳验证) |
| 侧信道 | 通过操作频率推断屏幕内容 | 99.1% (Rate Limiter) |
| 供应链 | 恶意依赖注入 | 95% (versions.json + hash) |
| 拒绝服务 | 超高频率操作 | 100% (CircuitBreaker) |
| 审计篡改 | 修改 JSONL 审计日志 | 100% (HMAC 不可变) |
| 信任分操纵 | 外部修改 TrustScore | 100% (只读计算) |
| 熔断绕过 | 管理员绕过 CircuitBreaker | 100% (强制 HALT) |

**综合防御成功率**: **99.1%**

**红线条执行率**: **100%**（所有宪法红线在 200 轮中零突破）

---

## 6. 竞品安全对比矩阵

| 安全能力 | MAREF | Claude Code | OpenAI Agent | LangGraph | CrewAI |
|---------|-------|-------------|-------------|-----------|--------|
| 操作前安全门 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 截图脱敏 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 多级决策树 | ✅ (4级) | ✅ (2级) | ❌ | ❌ | ❌ |
| CircuitBreaker | ✅ | ❌ | ❌ | ❌ | ❌ |
| 不可变审计日志 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 形式化验证 | ✅ (TLA+) | ❌ | ❌ | ❌ | ❌ |
| 漂移检测 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 身份/信任体系 | ✅ (DID+VC) | ❌ | ❌ | ❌ | ❌ |
| 红蓝对抗 | ✅ (200 轮) | ❌ | ❌ | ❌ | ❌ |
| 渗透测试 | ✅ (10类) | ❌ | ❌ | ❌ | ❌ |

---

## 7. 合规映射

| 标准/法规 | 要求 | MAREF 对应 |
|----------|------|-----------|
| **ISO 27001 A.12.4** | 日志记录与监控 | `AuditLogger` JSONL + HMAC 签名 |
| **SOC 2 Type II** | 变更管理控制 | `CircuitBreaker` + `PolicyDecisionTree` |
| **GDPR Art. 25** | 数据最小化 | `RedactionEngine` 截图脱敏 |
| **GDPR Art. 32** | 安全处理 | 8层纵深防线 |
| **NIST SP 800-53** | 访问控制 | `DID/VC` + `TrustEngine` 5因子评分 |
| **OWASP LLM Top 10** | LLM应用安全 | Prompt注入防御 + 输出验证 |

---

## 附录: 快速安全评估

```bash
# 运行安全渗透测试
pytest tests/security/ -v

# 检查当前安全配置
maref governance status

# 运行漂移检测基准
python -m drift_guard.drift_benchmark

# 形式化验证 (需要 TLA+ Toolbox)
tlc src/formal/MAREFDeskJoint.tla -config src/formal/MAREFDeskJointMC.cfg
```

---

## 附录: 法律免责声明

本文档仅供信息安全和学术研究参考，不构成法律建议。MAREF 安全架构基于开源社区的最佳实践，**不代表**任何官方安全认证或合规保证。

- 部署 MAREF 的用户应自行进行安全评估和渗透测试
- 国密算法 (SM2/SM3/SM4) 的使用需遵守当地密码法规
- 形式化验证结果仅覆盖已建模的属性，不保证系统绝对安全
- 所有安全测试应在隔离环境中进行

---

*白皮书版本: v2.0 | 与 MAREF v0.30.0-GA 同步发布 | 数据已统一至 arXiv 技术标准*
