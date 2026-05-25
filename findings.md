# MAREF 全栈击穿 — 研究发现与决策记录

> **用途**：记录调研发现、技术选型决策、避坑经验
> **更新规则**：每次有新发现立即追加，永不删除旧记录

---

## 发现 1: 代码库现状与文档十层映射（2026-05-24）

### 已有模块
| 文档十层 | 代码库对应路径 | 完成度评估 | 关键文件 |
|---------|--------------|-----------|---------|
| 编排层 | `src/maref/orchestration/` | ★ 已建，基础可用 | `dispatcher.py` |
| 执行层 | `src/maref/executor/` | 部分有 | `queue.py`, `api.py`, `scheduler.py` |
| 治理层 | `src/maref/governance/` + `gaas/` | 有审计+状态机 | `state_machine.py`, `audit.py` |
| 安全层 | `src/maref/security/` + `compliance/` | 有基础 | `trust_api.py`, `behavior_monitor.py` |
| 观测层 | `src/maref/observability/` | 有日志指标 | `logging.py`, `otel_middleware.py` |
| 交互层 | `gui/` + `desktop/` | 有GUI | `App.tsx`, `main.rs` |
| 基础设施 | `k8s/` + Dockerfile | 有部署配置 | - |
| 工具层 | `src/maref/tools/` | 基础工具管理 | `registry.py`, `tool_schema.py` |

### 完全缺失模块
- **人机协同层**：无专门模块，代码库中零实现
- **记忆层**：无专门模块，仅依赖LLM上下文窗口
- **技能市场层**：`tools/` 仅有基础工具管理，无注册中心/版本协商/信誉系统

### 决策记录
- **决策 1.1**：优先创建 `src/maref/human/`、`src/maref/memory/`、`src/maref/marketplace/` 三个新模块
- **决策 1.2**：不改动已有编排层核心代码，通过新增模块+接口适配方式集成
- **决策 1.3**：记忆层先以Redis+PostgreSQL起步，向量DB后续迭代引入

---

## 发现 2: 测试基线（2026-05-24）

```bash
pytest tests/ -v --cov=src/maref --cov-report=term-missing
# 结果：4 failed, 5992 passed, 9 skipped, 131 warnings in 716.87s
# 覆盖率：81.97%（Required 70.0% reached）
```

### 失败测试
| 测试文件 | 失败原因 | 严重程度 |
|---------|---------|---------|
| `test_r43_agent_handoff.py` | HandoffStatus.NACK vs REJECTED 不匹配 | 中 |
| `test_joint_machine.py` | 'JointStateMachine' object has no attribute 'barrier_version' | 中 |
| `test_plan_executor.py::test_execution_failure_skip` | FAILURE vs SUCCESS 断言失败 | 中 |
| `test_plan_executor.py::test_dependency_failure_skips_downstream` | IndexError: list index out of range | 中 |

### 低覆盖率模块（<70%）
| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `src/maref/security/keyring_store.py` | 22.73% | macOS Keychain封装，需集成测试 |
| `src/maref/stress/emergence_harness.py` | 0.00% | 涌现测试框架，未启用 |
| `src/maref/stress/resilience_tracker.py` | 35.48% | 韧性追踪器 |
| `src/maref/supply_chain/vulnerability_scanner.py` | 37.11% | 漏洞扫描器 |
| `src/maref/sidecar/terminal_bridge.py` | 16.54% | 终端桥接 |
| `src/maref/maref_lite/obs_cli.py` | 14.55% | 观测CLI |
| `src/maref/maref_lite/percv_cli.py` | 29.17% | PERCV CLI |

---

## 发现 3: 文档关键避坑要点汇总（2026-05-24）

### 人机协同层
- 弹窗地狱 → 批量确认 + 智能聚合
- 黑箱失控 → HATL模式也必须输出自主决策日志
- 紧急制动失灵 → 中断协议必须带全局序列号
- 模式切换死锁 → 模式切换本身是HATL级别操作

### 记忆层
- 把上下文窗口当记忆 → 上下文是缓存，所有关键状态必须外部持久化
- 记忆污染 → 记忆必须带置信度标签和来源标注
- 记忆孤岛 → 记忆层必须是中心化服务，不允许私有记忆
- 记忆膨胀 → 分层衰减：热(7天)→温(7-90天)→冷(>90天)
- 隐私泄漏 → 记忆必须带用户隔离标签

### 技能市场层
- 技能碎片化 → 技能聚合：相似Skill合并为官方推荐版
- 版本地狱 → 强制向后兼容期90天
- 质量失控 → 注册前三关：静态扫描+沙箱测试+人工审核
- 依赖黑洞 → 维护依赖图，下架前通知下游
- 经济模型欺诈 → 检测异常调用模式，自动冻结

---

## 发现 4: 技术选型待决策项（2026-05-24）

| 决策项 | 选项A | 选项B | 选项C | 建议 |
|--------|-------|-------|-------|------|
| 容器沙箱 | gVisor | Firecracker | Kata Containers | 先评估Firecracker启动时间 |
| 向量DB | pgvector | Milvus | Weaviate | 先用pgvector降低复杂度 |
| 规则引擎DSL | 自研 | OPA/Rego | CEL | 推荐OPA，成熟且可版本管理 |
| 消息队列 | Redis Pub/Sub | RabbitMQ | Kafka | 先用Redis Pub/Sub，与记忆层统一 |
| 对象存储 | MinIO | S3 | 本地磁盘 | 开发期MinIO，生产S3 |

---

## 发现 5: 接口契约草案（2026-05-24）

### Human Decision API
```python
POST /api/v1/human/decision
{
    "task_id": "uuid",
    "context": { /* 任务上下文 */ },
    "options": ["approve", "reject", "escalate"],
    "timeout": 300,  // 秒
    "urgency": "high" | "medium" | "low",
    "mode": "sync" | "async"
}
```

### IntentEvent Schema
```python
{
    "source": "websocket" | "http" | "voice" | "api",
    "user_id": "uuid",
    "raw_input": "...",
    "timestamp": "ISO8601",
    "session_context": {
        "session_id": "uuid",
        "device_id": "...",
        "history_pointer": "..."
    }
}
```

### Skill Manifest
```json
{
    "name": "...",
    "version": "1.0.0",
    "description": "...",
    "input_schema": { /* JSON Schema */ },
    "output_schema": { /* JSON Schema */ },
    "dependencies": ["skill://name@version"],
    "author": "...",
    "license": "Apache-2.0"
}
```

---

## 发现 6: 国密模块选型与实现（2026-05-24）

### 选型决策

| 选项 | 库 | 状态 | 结论 |
|------|-----|------|------|
| A | `gmssl` (py-gmssl) | ✅ PyPI 可用，纯 Python | **选用** |
| B | `tongsuo` (铜锁) | ❌ PyPI 无包 | 排除 |
| C | 自研 ctypes 绑定 | 工程量大 | 备选 |

**决策**：选用 `gmssl>=3.2.2` 作为国密基础库，已添加到 `identity` 可选依赖。

### 实现状态

| 算法 | 文件 | 功能覆盖 | 测试 |
|------|------|----------|------|
| SM2 | `src/maref/crypto/sm2.py` | 加密、解密、签名、验证 | ✅ 3/3 passed |
| SM3 | `src/maref/crypto/sm3.py` | 哈希、HMAC | ✅ 3/3 passed |
| SM4 | `src/maref/crypto/sm4.py` | CBC 加解密 | ✅ 2/2 passed |
| AIA 适配 | `src/maref/crypto/aia_adapter.py` | CAI 验证、CertificateVerify | ✅ 6/6 passed |

### gmssl 已知限制

1. **`sm3_hash()` 输入格式**：需要 `list(bytes)` 而非 `bytes`，已在封装层处理
2. **`sign_with_sm3()` 需双钥**：CryptSM2 实例必须同时持有公钥和私钥，签名 API 已适配
3. **无 SM2 密钥对生成**：`gmssl` 未暴露 EC 点乘接口，生产环境需预生成密钥对或集成更底层库
4. **许可证**：`gmssl` 采用类 BSD 许可证，与 Apache-2.0 兼容

### ACPs AIA 协议适配

已实现：
- `AgentIdentityCertificate` 数据结构（对应 CAI）
- `verify_cai_certificate()` — CASP 签名验证
- `generate_certificate_verify()` / `verify_certificate_verify()` — mTLS 握手签名
- `check_agent_identity()` — AIC 比对

待完成（需 AIP 先锋计划测试环境）：
- 真实 CASP 证书链验证
- 与 ACPs SDK 的端到端互通测试
- SM4 GCM 模式（如 AIA 协议需要）

---

## 待验证假设

1. **假设 A**：Redis Pub/Sub 能满足工作记忆的实时同步需求（需验证消息丢失场景）
2. **假设 B**：Firecracker 启动时间能控制在 500ms 以内（需基准测试）
3. **假设 C**：PostgreSQL + pgvector 能支撑语义记忆的初期需求（需验证检索延迟）
4. **假设 D**：OPA/Rego 的 DSL 能被非技术人员理解（需用户测试）
5. **假设 E**：`gmssl` Python 实现性能能满足 AIA 握手延迟要求（<100ms）（需基准测试）

---

## 外部参考

- [Open Policy Agent](https://www.openpolicyagent.org/)
- [Firecracker MicroVM](https://firecracker-microvm.github.io/)
- [OpenTelemetry for Agents](https://opentelemetry.io/)
- [MCP Protocol](https://modelcontextprotocol.io/)
