# MAREF 部署手册

## 环境要求

- Python 3.10+
- pip 23.0+
- Git 2.30+
- Node.js 20+ (GUI 构建)
- pnpm 10+ (GUI 构建)
- Rust stable (Tauri 构建, 可选)
- (可选) Docker 24.0+

## 快速部署

### 1. 克隆仓库

```bash
git clone https://github.com/maref-org/maref.git
cd maref
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -e ".[dev]"
```

### 4. 运行测试

```bash
pytest
```

## GUI 部署

### 开发模式

```bash
cd gui
pnpm install
pnpm dev
```

### 生产构建

```bash
cd gui
pnpm build
pnpm preview
```

### Tauri 桌面应用构建

```bash
cd gui
pnpm tauri build
```

构建产物位于 `gui/src-tauri/target/release/bundle/`。

## 生产环境部署

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"

EXPOSE 8080
CMD ["python", "-m", "src.sidecar.server"]
```

构建并运行：

```bash
docker build -t maref:latest .
docker run -p 8080:8080 maref:latest
```

### 配置说明

创建 `.env` 文件：

```env
MAREF_LOG_LEVEL=INFO
MAREF_BUFFER_SIZE=10000
MAREF_POLL_INTERVAL=1.0
MAREF_DRIFT_CHECK_INTERVAL=60.0
MAREF_REVIEW_TIMEOUT=300.0
MAREF_SAFETY_LEVEL=production
```

### 系统集成

#### 接入现有 Agent 框架

实现 `AgentAdapter` 接口：

```python
from src.sidecar.collector import AgentAdapter
from src.sidecar.protocol import AgentId, AgentState, EntropyReading, StateSnapshot

class MyFrameworkAdapter(AgentAdapter):
    async def list_agents(self) -> list[AgentId]:
        return [AgentId(name="agent-1", namespace="prod")]

    async def get_state(self, agent_id: AgentId) -> StateSnapshot | None:
        return StateSnapshot(
            agent_id=agent_id,
            timestamp=time.time(),
            state=AgentState.RUNNING,
            current_task="processing",
            task_progress=0.5,
            pending_messages=0,
        )

    async def get_entropy(self, agent_id: AgentId) -> EntropyReading | None:
        return EntropyReading(
            source=str(agent_id),
            timestamp=time.time(),
            value=1.2,
            threshold=4.0,
            level="normal",
        )
```

#### 启动治理覆盖层

```python
import asyncio
from src.maref_lite.governance import GovernanceOverlay
from src.sidecar.collector import ObservationCollector

async def main():
    adapter = MyFrameworkAdapter()
    collector = ObservationCollector(adapter, poll_interval=5.0)

    overlay = GovernanceOverlay(collector=collector)
    await overlay.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## 回滚指南

### K8s 部署回滚

```bash
# 使用回滚脚本
bash scripts/rollback.sh v0.25.0

# 或使用 kubectl 直接操作
kubectl rollout undo deployment/maref-desktop-agent -n maref
kubectl rollout status deployment/maref-desktop-agent -n maref
```

### 本地部署回滚

```bash
# 1. 切换到上一版本
git checkout tags/v0.25.0

# 2. 重新安装依赖
pip install -e ".[dev]"

# 3. 验证
pytest

# 4. 重启服务
python -m src.sidecar.server
```

### Tauri 桌面应用回滚

桌面应用通过内置自动更新机制回滚。如果新版本出现问题：

1. 应用会自动检测到更新失败并保留旧版本
2. 用户在设置中可以触发"检查更新"查看可用版本
3. 手动降级：从 [GitHub Releases](https://github.com/maref-org/maref/releases) 下载旧版本安装包

## 监控与告警

### 健康检查端点

Sidecar HTTP 服务器提供：

- `GET /health` — 健康状态
- `GET /metrics` — Prometheus 格式指标
- `GET /status` — 完整治理状态

### 日志配置

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
```

### 告警响应

参见 [Runbook 目录](runbook/README.md) 了解各告警的响应步骤：

| 告警名称 | 严重级别 | Runbook |
|---------|---------|---------|
| `MarefSidecarDown` | P0 | [RB-001](runbook/rb-001-sidecar-down.md) |
| `MarefGovernanceLatencyHigh` | P1 | [RB-002](runbook/rb-002-governance-latency.md) |
| `MarefDriftDetected` | P1 | [RB-003](runbook/rb-003-drift-detected.md) |
| `MarefAuditLogFailure` | P0 | [RB-004](runbook/rb-004-audit-log-failure.md) |
| `MarefMemoryGrowthAbnormal` | P1 | [RB-005](runbook/rb-005-memory-growth.md) |

## 发布流程

### 发布前检查

每次发布前运行：

```bash
bash scripts/release-check.sh
```

该脚本将自动检查测试通过率、覆盖率、代码风格、安全扫描等门禁条件，输出 Go/No-Go 决策。

### 发布审批矩阵

参见 [发布审批矩阵](release-approval-matrix.md) 了解不同发布类型的审批要求：

- **Hotfix**: CI 门禁 ✓ → 立即修复
- **Patch**: CI 门禁 ✓ → 技术负责人审批
- **Minor**: CI 门禁 ✓ → 技术负责人 + 安全审批
- **Major**: CI 门禁 ✓ → 全体验收 (Go/No-Go)

### 发布后监控

参见 [发布后监控检查清单](post-release-monitoring-checklist.md)，需在 T+1h、T+24h、T+7d、T+30d 分别执行检查。

## 故障排查

### 常用诊断命令

```bash
# 测试失败 — 查看详细错误
pytest -x -v

# 类型检查失败
mypy src/ tests/

# 代码风格检查
ruff check .
ruff format .

# 覆盖率报告
pytest --cov=src --cov-report=html
open htmlcov/index.html  # macOS
```

### 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 测试收集错误 (ERROR) | 根目录包污染 | 检查 `sidecar/` 等根目录包是否存在 |
| ImportError | 依赖未安装 | 运行 `pip install -e ".[dev]"` |
| Tauri 构建失败 | Rust 工具链问题 | 运行 `rustup update` |
| Sidecar 无法启动 | 端口被占用 | 修改端口或 `kill` 占用进程 |
| 覆盖率低于门限 | 新代码缺少测试 | `coverage report --show-missing` 查看未覆盖行 |
| ruff 问题过多 | 代码风格不一致 | `ruff check --fix src/` 自动修复 |
| mypy 类型错误 | 类型注解缺失 | 使用 `Any` 或正确类型注解 |

### 性能调优

- 调整 `buffer_size` 控制内存使用
- 调整 `poll_interval` 平衡实时性与开销
- 使用 `num_bins` 控制漂移检测精度

## 升级指南

```bash
git pull origin main
pip install -e ".[dev]"
pytest
```

## 安全建议

- 生产环境使用 HTTPS
- 限制 `/health` 和 `/metrics` 访问
- 定期轮换 API 密钥
- 启用审计日志
- 详见 [安全策略](../SECURITY.md)
