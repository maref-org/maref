# MAREF v0.35.0-beta Release Notes

> **双轨并行**: 独立递归（工程质量） × Loop Engineering 集成（叙事 + 差异化）

---

## 轨道 1 — 工程质量

### 覆盖率工程 (T1-S1)
- `obs_bridge.py`: 24% → **94%**
- `sidecar/server.py`: 10% → **63.59%** (governance/audit/immunity/HITL endpoints)
- `mcp_bridge.py`: 24% → **43.54%**
- `browser_controller.py`: 全新测试覆盖，7 方法 + 边界场景
- 新增 MCP 集成测试：MCP → Governance → Audit 完整调用链

### OSS 文档 (T1-S2)
- `docs/oss-todo.md` — S0 执行待办清单（填补 AGENTS.md 引用空白）
- `docs/oss-execution-norm-v1.0.md` — Track B Agent 执行规范
- `docs/api.md` — 新增 MCP 协议端点文档 + 调用示例
- 版本一致性锁：Cargo.toml 0.28.0-rc → 0.34.0-rc

## 轨道 2 — Loop Engineering 集成

### 架构
- **Loop Engineering 叙事框架**: 治理是 Loop 进入生产的先决条件
- **Verifier 治理**: 多 Agent 交叉验证 + 评估器绩效追踪（解决 Loop 的 Verifier 瓶颈）
- **MAREFLoop 适配器**: 5 行代码集成 MAREF 治理到任意 Loop

### 竞品定位
| 维度 | MAREF v0.35.0 | 竞品状态 |
|------|---------------|---------|
| TLA+ 形式化验证 | ✅ 5 条宪法红线 | 零竞品 |
| Loop 治理层 | ✅ MAREFLoop 适配器 | Google ADK 2.0 ⚠️ |
| Verifier 交叉验证 | ✅ 新增 | 零竞品 |
| GitHub Stars | 目标 > 100 | 竞品 7K-27K |

---

## 门禁

| 门禁 | 状态 |
|------|------|
| Ruff | 0 errors ✅ |
| Mypy strict | 0 errors ✅ |
| 测试 | 63 passed (新增 4 个测试文件) |
| 覆盖率 (侧车) | obs_bridge 94%, server 63.59% |
| 安全 P0 阻塞 | 0 (与 v0.34.0 同) |
| OSS 文档 | oss-todo.md + oss-execution-norm-v1.0.md ✅ |
| 版本一致性 | 全部统一到 0.35.0-beta ✅ |

---

## 已知问题

- 前端 E2E 测试尚未 CI 集成 (Playwright)
- GUI 覆盖率待补充
- on-call / Runbook 运维基础设施未建立（当前为框架级发布，非 7×24 SaaS）
