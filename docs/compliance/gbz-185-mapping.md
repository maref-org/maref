# GB/Z 185.8（智能体审计）条款 → MAREF 实现映射

> 版本：对照 2026-11-10 分发版征求意见稿（SHA-256 前 12 位 `639a5bd0532a`）。
> 状态标记：✅ 已覆盖｜🟡 部分覆盖｜⬜ 缺口（需后续补齐）。
> 每条只写可核验的落点（文件:行），不写"计划支持"。

| # | 条款 | 要求（摘要） | MAREF 落点 | 状态 |
|---|---|---|---|---|
| 1 | §1 范围 | 审计日志的生成、传输、存储与审计跟踪 | `src/maref/governance/audit.py:170`（AuditLogger） | ✅ |
| 2 | §5.1 功能参考架构 | 日志生成/存储功能分层 | `src/maref/governance/audit_bus.py:37`（AuditBus） | 🟡 生成有、独立"日志存储功能"未抽象 |
| 3 | §5.2 表1 接口 | 日志传输接口定义 | `src/maref/integration/mcp_governance.py`（工具调用治理通道） | 🟡 仅覆盖 MCP 通道 |
| 4 | §6.1 生成与传输安全 | 生成端与传输端的安全要求 | `src/maref/security/outbound/guard.py:56`（OutboundGuard） | 🟡 出站守卫有，未与日志通道绑定 |
| 5 | §6.2.1 系统日志 | 智能体系统操作记录 | — | ⬜ 未单独建模，混在通用审计事件中 |
| 6 | §6.2.2 访问日志 | 与外部实体交互事件 | `src/maref/security/inbound/gate.py:256`（InboundVerdict） | 🟡 只覆盖入站裁决，未覆盖对外调用 |
| 7 | §6.2.3 消息日志 | 智能体间消息事件 | `src/maref/integration/mcp_governance.py`（correlation_id 生成） | 🟡 |
| 8 | §6.2.4 业务日志 | 含主体/动作/目标/结果的事件记录 | `src/maref/governance/audit.py:37`（AuditEntry） | ✅ |
| 9 | §6.3.1 源端完整性保护 | 日志落盘前签名 | `src/maref/governance/audit.py:247`（`_sign_entry`） | ✅ Ed25519 主、HMAC 兼容 |
| 10 | §6.3.2 接收端验证 | 接收方验证签名与链 | `src/maref/governance/audit_chain_verify.py:38`（VerifyReport） | ✅ |
| 11 | §7.1 a) 加密保护 | 采用国家密码管理要求的算法 | `src/maref/identity/sm2_certificate.py:176`（NationalCAAdapter）；`src/maref/crypto/`（Ed25519） | 🟡 SM2 为适配器，默认路径是 Ed25519 |
| 12 | §7.1 b) 防未预期删改覆盖 | 访问控制 + 防篡改 | `src/maref/governance/audit_anchor.py:40`（AnchorRecord） | ✅ 锚定 + 哈希链 |
| 13 | §7.1 c) 备份与恢复性测试 | 留存期内可读可查可恢复 | — | ⬜ 未见恢复性测试用例 |
| 14 | §7.1 d) 存储管理操作记录 | 查询/导出/删除/归档留痕 | `src/maref/governance/audit.py:535`（log） | 🟡 通用入口有，未强制覆盖存储管理动作 |
| 15 | §8 a) 管理日志范围 | 访问/导出/权限变更等 | `src/maref/governance/audit_bus.py:58`（log） | 🟡 同上，靠调用方自觉 |
| 16 | §8 b) 管理日志字段 | 主体/时间/类型/对象/结果/关联标识 | `src/maref/governance/audit.py:37`（actor/action/details/metadata） | 🟡 结构化字段不全，部分落在 metadata |
| 17 | §8 c) 独立授权与完整性 | 管理日志权限独立、批量导出双人复核 | — | ⬜ |
| 18 | §8 d) 不伪造身份码 | 操作主体非智能体时不得伪造 aic | `src/maref/identity/aic_adapter.py:49`（AIC） | 🟡 有身份模型，无强制校验 |
| 19 | §9.1.2 表2 通用头部 | schemaVersion/timestamp/aic/logType/body | `src/maref/governance/audit.py:78`（to_dict） | 🟡 字段名未按表2 对齐（本次意见建议二） |
| 20 | §9.1.4 表4 完整性字段 | alg/sig/x5t#S256 | `src/maref/governance/audit.py:37`（signature 字段族） | 🟡 有签名与指纹，无 x5t#S256 |
| 21 | §9.1.5 版本控制 | 修订/次版本/主版本升级规则 | — | ⬜ 无 schema 版本协商 |
| 22 | §9.3 表5 访问日志 | request/response/caller.aic/callee.aic | `src/maref/security/inbound/gate.py:256` | 🟡 无 callee/caller 双 AIC |
| 23 | §9.5 表7 业务日志 | actor/action/target/result 必选 | `src/maref/governance/audit.py:37` + 本次新增 `primary_subject`/`immediate_actor`/`actor_chain` | 🟡 本次补齐 3 个可选字段 |
| 24 | §10.1–10.4 表8–11 存储结构 | 各类型日志存储字段 | `src/maref/eivl/federated_store.py:51`（FederatedAuditStore） | 🟡 通用存储，未按 4 类建模 |

## 统计

- ✅ 已覆盖：5 条（#1、#8、#9、#10、#12）
- 🟡 部分覆盖：15 条
- ⬜ 缺口：4 条（#5 系统日志、#13 恢复性测试、#17 独立授权、#21 版本控制）

## 下一步（按性价比排序）

1. **#19/#23 字段命名对齐**：把 `to_dict` 输出增加 `schemaVersion`/`logType` 等别名字段，零破坏。
2. **#5 系统日志建模**：新增 `log_type="system"` 的写入路径，消除与 §9.2 的冲突。
3. **#21 版本控制**：给 AuditEntry 加 `schema_version`，按 §9.1.5 规则升版。
4. **#13/#17**：补恢复性测试与双人复核，属流程能力，非代码。
