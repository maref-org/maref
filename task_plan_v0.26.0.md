# MAREF v0.26.0-rc 迭代实施方案

## 版本定位：桌面闭环贯通 + 全栈链路贯通 + 生产就绪

**版本口号**: "从 Demo 到 Product" — 让 MAREF 桌面 Agent 从功能展示走向生产可用

---

## 一、现状审计（基于 v0.25.0-rc 基线）

### 已完成（v0.24.0 → v0.25.0）
- ✅ P0 安全清零（Electron hardenedRuntime, entitlements, ErrorBoundary）
- ✅ AuditLogger HMAC-SHA256 防篡改签名
- ✅ Sidecar MCP 协议标准化（5 Tools + 4 Resources + 2 Prompts）
- ✅ Electron 构建配置加固（asar, multi-arch, compression）
- ✅ 知识基础设施（AGENTS.md, knowledge-library, vault signals）
- ✅ 测试通过率 99.9%（4092/4096）

### 桌面端现状（v0.25.0）
| 能力 | 状态 | 缺口 |
|------|------|------|
| GUI 框架 | Electron + React 19 + TypeScript 完整 | CSP=null（已修复） |
| OmniParser v3 | 接入截图→解析→操作 | 未贯通到真实桌面操控 |
| 安全门 | ACTIVE, 5 应用白名单, 13 危险关键词 | 未连接后端决策树 |
| 操作历史 | 记录截图/click/type/hotkey/scroll | 仅展示，未持久化 |
| 可用操作 | 8 种（CLICK 到 WAIT） | Mock 层为主 |
| 治理看板 | 存在导航入口 | 未实现 |
| 审计日志 | 存在导航入口 | 未连接 AuditLogger |
| 漂移检测 | 存在导航入口 | 未实现 |
| 信任评分 | 存在导航入口 | 未实现 |

### 待完成任务（从 v0.25.0 顺延）
- R2: 桌面核心闭环未贯通（P0 阻断）
- R3: 无可观测性（P0 阻断）
- R6: GUI 错误边界（✅ 已修复 v0.25.0）
- R7: 全栈链路未贯通（P1）
- R8: 双壳架构维护成本高（P1）
- R9: Docker 版本滞后 + root 运行（P1）
- R10: 无 i18n/a11y/离线（P2）
- R11: 无安全扫描自动化（P1）
- R12: 无 RUM/性能预算 CI（P1）
- R13: 审计日志 HMAC 签名（✅ 已修复 v0.25.0）
- R14: K8s HPA 目标名不匹配（P1）
- R16: GUI 图标文件为空（P2）
- R17: Electron hardenedRuntime=false（✅ 已修复 v0.25.0）
- R18: MCP SSE 传输为 stub（P2）
- R19: Docker 安装 dev 依赖到生产镜像（P1）

---

## 二、v0.26.0 核心目标

### 目标 1: 桌面核心闭环贯通（P0 → 完成态）
**定义**: 截图→解析→操作→验证 全链路真实运行，非 mock

**子任务**:
1. **OmniParser v3 真实接入**
   - 当前: GUI 展示 OmniParser v3 状态，操作历史有记录
   - 缺口: OmniParser 输出未连接到实际桌面操作执行器
   - 方案: 实现 `DesktopController.execute()` 真实调用 PyAutoGUI/pyobjc
   - 验收: 端到端录制 10 步操作序列，回放验证 100% 成功率

2. **操作历史持久化**
   - 当前: 操作历史仅在内存中展示
   - 缺口: 无持久化存储，重启丢失
   - 方案: SQLite + 时间戳索引 + 操作快照
   - 验收: 重启后操作历史完整恢复

3. **安全门 → 决策树连接**
   - 当前: 安全门 ACTIVE 状态显示，但未连接 `PolicyDecisionTree`
   - 缺口: 危险关键词检测 13 项，未连接四级决策树（Rule→Mode→SafetyGate→User）
   - 方案: GUI 安全门状态与后端决策树实时同步
   - 验收: 危险操作触发 HITL 中断，用户确认后继续

### 目标 2: 全栈链路贯通（P1）
**定义**: 前端类型自动生成 + Trace 贯通 + 端到端可观测性

**子任务**:
1. **OpenTelemetry Trace 贯通**
   - 前端: React instrumentation 自动追踪用户操作
   - 后端: FastAPI OTel middleware 追踪 API 请求
   - Sidecar: MCP 工具调用 Trace ID 传递
   - 验收: 单个用户操作可追溯完整调用链（前端→后端→Sidecar→治理层）

2. **RED 指标面板**
   - Rate: 请求/操作 QPS
   - Errors: 失败率（按错误码分类）
   - Duration: P50/P95/P99 延迟
   - 验收: 治理看板实时展示 RED 指标

3. **API 类型自动生成**
   - 后端 FastAPI 生成 OpenAPI schema
   - 前端自动生成 TypeScript 类型和 client
   - 验收: 前后端类型 100% 对齐，零手动维护

### 目标 3: 生产就绪（P0/P1 清零）
**定义**: 从 Beta 早期（5.5/10）提升到 Pre-GA（7.5/10）

**子任务**:
1. **安全扫描 CI 自动化**
   - Bandit（Python 静态扫描）
   - Semgrep（跨语言扫描）
   - Trivy（容器镜像扫描）
   - 验收: PR 门禁，高危漏洞阻断合并

2. **Docker 多阶段构建**
   - 修复: dev 依赖进入生产镜像
   - 修复: root 用户运行
   - 验收: 镜像体积 < 500MB，非 root 用户

3. **K8s HPA 修复**
   - 修复目标名不匹配
   - 验收: HPA 正常扩缩容

4. **Tauri 双壳架构评估**
   - 当前: Tauri + Electron 两套壳
   - 决策: 保留 Electron 主构建（功能更完整）
   - 方案: Tauri 降级为可选轻量构建
   - 验收: 维护成本降低 50%（单主构建目标）

---

## 三、Factory Missions 融合执行计划

### 版本架构
```
v0.26.0-rc
├── Phase D: 桌面闭环贯通（4 周）
── Phase O: 全栈可观测性（3 周）
├── Phase P: 生产就绪清零（2 周）
── Phase I: 集成验证（1 周）
```

### Phase D: 桌面闭环贯通（Week 1-4）

**D1: DesktopController 真实执行器**
- Orchestrator: Opus 4.6（架构设计）
- Worker: Sonnet 4.6（PyAutoGUI/pyobjc 执行器实现）
- Validator: GPT-5.3-Codex（代码审查）
- Token 预算: 3M, $300

**D2: 操作历史持久化**
- Worker: Kimi K2.6（SQLite 存储实现）
- Validator: Gemini 2.5 Pro（Schema 验证）
- Token 预算: 2M, $150

**D3: 安全门→决策树连接**
- Worker: Sonnet 4.6（前端安全门与后端决策树桥接）
- Validator: GPT-5.3-Codex（HITL 中断流程验证）
- Token 预算: 2.5M, $250

**D4: 治理看板实现**
- Worker: Sonnet 4.6（React 看板组件）
- Validator: Gemini 2.5 Pro（UI/UX 验证）
- Token 预算: 3M, $300

### Phase O: 全栈可观测性（Week 5-7）

**O1: OpenTelemetry Trace 贯通**
- Worker: Sonnet 4.6（OTel instrumentation）
- Validator: GPT-5.3-Codex（Trace ID 传递验证）
- Token 预算: 4M, $400

**O2: RED 指标面板**
- Worker: Kimi K2.6（指标收集和展示）
- Validator: Gemini 2.5 Pro（准确性验证）
- Token 预算: 2.5M, $200

**O3: API 类型自动生成**
- Worker: Sonnet 4.6（OpenAPI → TypeScript codegen）
- Validator: GPT-5.3-Codex（类型对齐验证）
- Token 预算: 2M, $200

### Phase P: 生产就绪清零（Week 8-9）

**P1: 安全扫描 CI**
- Worker: Kimi K2.6（Bandit/Semgrep/Trivy 集成）
- Validator: GPT-5.3-Codex（扫描结果验证）
- Token 预算: 1.5M, $120

**P2: Docker 多阶段构建**
- Worker: Kimi K2.6（Dockerfile 重写）
- Validator: GPT-5.3-Codex（镜像验证）
- Token 预算: 1M, $80

**P3: K8s HPA 修复**
- Worker: Kimi K2.6（HPA 配置修复）
- Validator: GPT-5.3-Codex（扩缩容验证）
- Token 预算: 0.5M, $50

**P4: Tauri 双壳架构决策**
- Worker: Sonnet 4.6（架构评估报告）
- Validator: Opus 4.6（决策评审）
- Token 预算: 1M, $100

### Phase I: 集成验证（Week 10）

**I1: 端到端桌面操作验证**
- 录制 10 步操作序列
- 回放验证 100% 成功率
- Token 预算: 0.5M, $50

**I2: 全链路 Trace 验证**
- 单操作追溯完整调用链
- Token 预算: 0.5M, $50

**I3: 自举验证**
- Kimi K2.6 实现
- Opus 4.6 + GPT-Codex + Gemini 2.5 联合验证
- Token 预算: 1M, $100

---

## 四、Token 预算预估

| Phase | Features | Token 预估 | $ 成本 |
|-------|----------|-----------|--------|
| Phase D | D1-D4 | 10.5M | $1,000 |
| Phase O | O1-O3 | 8.5M | $800 |
| Phase P | P1-P4 | 4M | $350 |
| Phase I | I1-I3 | 2M | $200 |
| **总计** | **14 features** | **25M** | **$2,350** |

含 50% 缓冲: 37.5M Token, $3,525

---

## 五、验收标准

### 桌面闭环
- [ ] 10 步操作序列录制+回放 100% 成功率
- [ ] 操作历史重启后完整恢复
- [ ] 危险操作触发 HITL 中断，用户确认后继续
- [ ] 治理看板实时展示治理状态

### 全栈可观测性
- [ ] 单操作可追溯完整调用链（前端→后端→Sidecar→治理层）
- [ ] RED 指标实时展示（P95 < 500ms）
- [ ] 前后端类型 100% 对齐

### 生产就绪
- [ ] PR 门禁：高危漏洞阻断合并
- [ ] Docker 镜像 < 500MB，非 root 用户
- [ ] HPA 正常扩缩容
- [ ] 单主构建目标（Electron），Tauri 可选

### 测试指标
- 测试通过率: ≥ 99.5%
- 覆盖率: ≥ 85%（核心模块）
- 新增测试: ≥ 200

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| PyAutoGUI macOS 权限问题 | 中 | 高 | 提前申请 Accessibility 权限，提供引导流程 |
| OTel 性能开销 | 低 | 中 | 采样率可调，默认 10% |
| Docker 多阶段构建增加复杂度 | 低 | 低 | 保留单阶段 fallback |
| 端到端测试环境不稳定 | 中 | 中 | CI 使用专用 macOS runner |

---

## 七、知识基础设施

### .missions 目录
```
.missions/v0.26.0-desktop-closed-loop/
── mission.json          # 10 milestones (m0-m9)
├── features.json         # 14 features tracking
├── validation-contract.md # Behavior assertions
├── features/
│   ├── D1_desktop_controller/
│   ├── D2_operation_history/
│   ├── D3_safety_gate_bridge/
│   ├── D4_governance_dashboard/
│   ├── O1_otel_trace/
│   ├── O2_red_metrics/
│   ├── O3_api_types/
│   ├── P1_security_ci/
│   ├── P2_docker_multistage/
│   ├── P3_k8s_hpa/
│   ├── P4_tauri_decision/
│   ├── I1_e2e_validation/
│   ├── I2_trace_validation/
│   └── I3_self_verification/
└── knowledge/            # Implementation notes
```

### Vault 更新
- `vault/signals/S-20260516-002.yaml` — v0.26.0 规划信号
- `vault/kdps/K-20260516-010.yaml` — Tauri vs Electron 决策记录

---

## 八、执行纪律

### Handoff Discipline
每个 Feature 完成后:
1. 运行 `pytest tests/ -v --cov` — 覆盖率 ≥ feature 阈值
2. Git commit: `feat(module): description`
3. 更新 `features.json`
4. 在 `knowledge/` 留下实现笔记
5. 通过独立 Validator 验证

### 安全规则
- 不可降级安全断言
- 所有桌面操作必须经过安全门
- HITL 中断不可绕过
- 审计日志必须 HMAC 签名

### 验证轮次
- Phase D: 每个 Feature 2-3 轮验证
- Phase O: 每个 Feature 2 轮验证
- Phase P: 每个 Feature 1-2 轮验证
- Phase I: 3 轮全量验证

---

**版本时间线**: 10 周（2026-05-20 → 2026-07-30）
**预计 Token 消耗**: 25M（含缓冲 37.5M）
**预计成本**: $2,350（含缓冲 $3,525）
**目标评分**: 7.5/10（Pre-GA）