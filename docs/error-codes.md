# MAREF Error Codes

> AGENTS.md 引用：`maref.exceptions.MAREFError` 错误码 (20 个 E0000–E4002)

| 错误码 | 名称 | 描述 | 模块 |
|--------|------|------|------|
| E0000 | INTERNAL_ERROR | 未分类内部错误 | core |
| E0001 | VALIDATION_ERROR | 输入验证失败 | core |
| E0002 | NOT_FOUND | 资源未找到 | core |
| E0003 | PERMISSION_DENIED | 权限不足 | security |
| E0004 | UNAUTHORIZED | 身份认证失败 | security |
| E0005 | RATE_LIMIT | 速率限制 | gateway |
| E0006 | CIRCUIT_OPEN | 熔断器打开 | governance |
| E0007 | STATE_INVALID | 状态机转换不合法 | governance |
| E0008 | TRUST_BOUNDARY | 跨信任域调用被拦截 | security |
| E0009 | AUDIT_FAILURE | 审计日志写入失败 | governance |
| E1000 | AGENT_NOT_FOUND | Agent 实例不存在 | recursive |
| E1001 | AGENT_UNAVAILABLE | Agent 当前不可用 | recursive |
| E1002 | AGENT_CAPACITY | Agent 容量已满 | recursive |
| E2000 | OBSERVATION_TIMEOUT | 观测超时 | observation |
| E2001 | OBSERVATION_INVALID | 观测数据无效 | observation |
| E3000 | DRIFT_DETECTED | 漂移超出阈值 | drift_guard |
| E3001 | DRIFT_INCONCLUSIVE | 漂移检测结果不确定 | drift_guard |
| E4000 | SIGNAL_INVALID | 外部信号格式无效 | sidecar |
| E4001 | MCP_PROTOCOL_ERROR | MCP 协议错误 | sidecar |
| E4002 | A2A_HANDSHAKE_FAILED | A2A 握手失败 | integration |

---

## 用法

```python
from maref.exceptions import MAREFError

try:
    result = governance.check("deploy")
except MAREFError as e:
    print(f"Error {e.code}: {e.message}")
```
