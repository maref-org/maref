# ADR-004: 指标存储持久化 — SQLite 主存储 + PostgreSQL 规划

**状态**: 已接受
**日期**: 2026-05-14
**决策者**: MAREF 架构组

## 背景

MAREF 治理系统产生多类指标数据（治理决策、安全门检查、成本追踪、遥测），需要一个持久化存储方案：

1. **多表结构**：四类指标（governance, guardrail, cost, telemetry）
2. **写入密集**：每次治理决策都需记录，写入量 >> 读取量
3. **轻量部署**：单节点部署无需复杂数据库
4. **未来扩展**：集群部署需支持 PostgreSQL

## 决策

**使用 SQLite 作为主要指标存储（WAL 模式），设计支持未来迁移到 PostgreSQL。四表结构统一设计，计划在 v0.40.0 引入 PostgreSQL 适配器。**

### Schema

```sql
CREATE TABLE governance_metrics (
  id INTEGER PRIMARY KEY,
  timestamp TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  labels TEXT,
  agent_id TEXT
);

CREATE TABLE guardrail_metrics (
  id INTEGER PRIMARY KEY,
  timestamp TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  labels TEXT,
  agent_id TEXT
);

CREATE TABLE cost_metrics (
  id INTEGER PRIMARY KEY,
  timestamp TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  labels TEXT,
  agent_id TEXT
);

CREATE TABLE telemetry_metrics (
  id INTEGER PRIMARY KEY,
  timestamp TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  labels TEXT,
  agent_id TEXT
);
```

### SQLite 配置

| 参数 | 值 | 理由 |
|------|----|------|
| journal_mode | WAL | 并发读写性能最佳 |
| synchronous | NORMAL | 平衡性能与持久性 |
| 默认路径 | `~/.maref/metrics.db` | 用户隔离，无需配置 |

### 关键设计决策

1. **时间戳字符串**：使用 ISO 8601 字符串 (`%Y-%m-%dT%H:%M:%SZ`) 而非 Unix 时间戳，便于人类可读和 SQL 查询
2. **labels JSON**：标签以 JSON 字符串存储，支持灵活维度查询
3. **跨表查询**：`query()` 方法支持指定表或搜索所有表
4. **聚合查询**：内置 AVG/SUM/MAX/MIN/COUNT 聚合
5. **数据清理**：`prune(retention_days=90)` 按保留期清理
6. **PostgreSQL 适配器接口**：`MetricStoreABC` 抽象基类（计划中）

### PostgreSQL 迁移路径（v0.40.0）

```python
# 计划接口
class MetricStoreABC(ABC):
    @abstractmethod
    def record(self, name, value, labels, agent_id, table): ...
    @abstractmethod
    def query(self, name, since, until, agent_id, limit, table): ...
    @abstractmethod
    def query_aggregate(self, name, operation, since, table): ...
    @abstractmethod
    def prune(self, retention_days): ...

class PostgresMetricStore(MetricStoreABC):
    # v0.40.0 实现
    ...
```

## 后果

- **正面**：零配置部署，开箱即用
- **正面**：WAL 模式支持治理系统的高写入负载
- **正面**：统一四表结构简化查询逻辑
- **正面**：90 天保留策略自动管理磁盘空间
- **负面**：SQLite 不支持水平扩展
- **负面**：JSON 标签字段无法在 SQL 层面高效过滤
- **负面**：大量数据时全文检索性能下降
- **缓解**：`prune()` 定期清理，索引计划在 v0.35.0 添加

## 实施检查项

- [x] MetricStore 核心实现
- [x] 四表 DDL
- [x] SQLite WAL 配置
- [x] 基础 CRUD（record, query, query_aggregate）
- [x] prune 清理
- [x] get_table_stats
- [ ] PostgreSQL 适配器（v0.40.0）
- [ ] 表索引（v0.35.0）
- [ ] 自动清理定时任务

## 替代方案

- **InfluxDB / TimescaleDB** — 被否决，对于单节点部署过于复杂，增加运维负担
- **JSON 文件存储** — 被否决，查询性能差，无并发安全
- **Redis** — 被否决，数据持久化有限，不适合历史查询
