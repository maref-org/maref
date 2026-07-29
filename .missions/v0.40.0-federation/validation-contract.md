# v0.40.0 Federation — Validation Contract

> **上游契约**: `docs/版本迭代规划/MAREF-v0.37.0-0.40.0-版本迭代规划-诚信到可验证闭环.md`

## 验收标准

### P0: 联邦审计生产就绪

| ID | 验收条件 | 验证方法 | 优先级 |
|----|---------|---------|--------|
| G-01 | FederatedMerkleAggregator 支持并发提交（threading.Lock / asyncio.Lock） | 并发测试 + 竞态检测 | P0 |
| G-02 | 联邦审计状态持久化到 SQLite/JSONL，重启后 Merkle 根一致 | 重启一致性端到端测试 | P0 |
| G-03 | `POST /api/v1/federated/submit` 接受组织审计日志并返回 Merkle 证明 | API 端到端测试 | P0 |
| G-04 | `GET /api/v1/federated/proof/{org_id}` 返回指定组织的 Merkle 包含证明 | API 测试 | P0 |
| G-05 | `GET /api/v1/federated/root` 返回最新全局 Merkle 根 | API 测试 | P0 |
| G-06 | Sidecar 支持 `marefd --federated` 模式启动联邦审计节点 | CLI 端到端测试 | P0 |
| G-07 | FederatedProof 支持序列化/反序列化（文件交换 / HTTP / MCP） | 单元测试 + 集成测试 | P0 |
| G-08 | 100 个组织 / 10000 条证明并发压测下正常响应 | 压测脚本 | P0 |
| G-09 | `maref federated verify` 离线验证通过率 100% | CLI 端到端测试 | P0 |

### P1: 政策合规映射

| ID | 验收条件 | 验证方法 | 优先级 |
|----|---------|---------|--------|
| G-10 | EU AI Act Article 12/13/14 合规映射文档完成 | 文档评审 | P1 |
| G-11 | 网信办"区块链可追溯机制"技术响应文档完成 | 文档评审 | P1 |
| G-12 | OWASP Agentic Top 10 ≥ 8/10 覆盖对照表（代码验证） | 扫描 + 代码审查 | P1 |

### P2: 递归自演进基础重构

| ID | 验收条件 | 验证方法 | 优先级 |
|----|---------|---------|--------|
| G-13 | 红蓝对抗引擎 ≥ 1 条验证路径基于真实治理管线（非模拟数据） | 代码审查 | P2 |
| G-14 | SelfBootstrapVerifier 从模式匹配改为基于 Merkle 审计链验证 | 代码审查 + 测试 | P2 |

### 质量门禁

| 门禁 | 阈值 | 验证 |
|------|------|------|
| ruff errors | 0 | `ruff check src/` |
| mypy errors | 0 | `mypy src/maref/` |
| 测试收集错误 | 0 | `pytest --collect-only` |
| 测试通过率 | 100% | `pytest tests/ -v` |
| 密钥泄漏 | 0 | `grep -r 'fallback.*key\|hardcoded.*secret' src/` |
| 联邦证明离线验证 | 100% | `maref federated verify` |

## 不做清单

- 不做社区 Skill 市场（v0.41.0+）
- 不做 Token 经济（v0.41.0+）
- 不做桌面 Agent 闭环增强（v0.40.0+）
- 不做覆盖率大幅提升（仅保持诚实，不追求数字）
