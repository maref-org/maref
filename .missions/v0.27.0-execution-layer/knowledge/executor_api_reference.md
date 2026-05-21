# Executor API 参考文档

## 概述
MAREF Executor 模块提供 RESTful API 用于任务提交、查询、管理。基于 FastAPI 框架，自动生成 OpenAPI schema。

## 快速启动

```bash
# 安装 sidecar 依赖（含 FastAPI）
pip install maref[sidecar]

# 启动 API 服务
python -c "
from fastapi import FastAPI
from maref.executor.queue import TaskQueue
from maref.executor.api import create_task_router

app = FastAPI()
queue = TaskQueue('/tmp/maref_tasks.db')
app.include_router(create_task_router(queue))

import uvicorn
uvicorn.run(app, host='0.0.0.0', port=8000)
"
```

## 端点列表

### 1. 创建任务
```
POST /api/v1/tasks
```

**请求体**:
```json
{
  "name": "my-task",
  "description": "任务描述",
  "priority": 1,
  "payload": {"key": "value"},
  "timeout_seconds": 300,
  "max_retries": 3,
  "tags": ["urgent", "backend"],
  "session_id": "sess-abc-123"
}
```

**响应** (201 Created):
```json
{
  "task_id": "uuid-string",
  "status": "queued",
  "created_at": "2026-05-21T12:00:00+00:00"
}
```

### 2. 获取任务
```
GET /api/v1/tasks/{task_id}
```

**响应** (200 OK):
```json
{
  "id": "uuid-string",
  "name": "my-task",
  "description": "任务描述",
  "priority": 1,
  "status": "queued",
  "payload": {},
  "created_at": "2026-05-21T12:00:00+00:00",
  "updated_at": "2026-05-21T12:00:00+00:00",
  "started_at": null,
  "completed_at": null,
  "timeout_seconds": 300,
  "max_retries": 3,
  "retry_count": 0,
  "error_message": null,
  "session_id": "sess-abc-123",
  "tags": ["urgent", "backend"]
}
```

### 3. 取消任务
```
POST /api/v1/tasks/{task_id}/cancel
```

**响应** (200 OK):
```json
{
  "task_id": "uuid-string",
  "status": "cancelled"
}
```

### 4. 任务列表
```
GET /api/v1/tasks?status=queued&priority=2&session_id=sess-abc&tag=urgent&limit=20&offset=0
```

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| status | string | - | 过滤状态 (pending/queued/running/completed/failed/cancelled/timeout) |
| priority | int | - | 过滤优先级 (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL) |
| session_id | string | - | 按会话过滤 |
| tag | string | - | 按标签过滤 |
| limit | int | 100 | 返回条数 (最大 1000) |
| offset | int | 0 | 分页偏移 |

**响应** (200 OK):
```json
{
  "tasks": [
    {
      "id": "uuid-string",
      "name": "my-task",
      "status": "queued",
      "priority": 2,
      ...
    }
  ],
  "total": 1
}
```

## 错误码

| 状态码 | 说明 | 场景 |
|--------|------|------|
| 201 | 创建成功 | POST /api/v1/tasks |
| 200 | 请求成功 | GET/POST 操作成功 |
| 404 | 资源不存在 | 任务 ID 不存在 |
| 409 | 状态冲突 | 取消已完成/失败的任务 |
| 422 | 参数验证失败 | priority 超出范围 |

## curl 示例

```bash
# 创建任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"name": "hello", "priority": 2}'

# 查询任务
curl http://localhost:8000/api/v1/tasks/{task_id}

# 取消任务
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/cancel

# 列表过滤
curl "http://localhost:8000/api/v1/tasks?status=queued&limit=10"
```

## 优先级说明

| 值 | 名称 | 说明 |
|----|------|------|
| 0 | LOW | 低优先级，后台任务 |
| 1 | MEDIUM | 中优先级，默认值 |
| 2 | HIGH | 高优先级，重要任务 |
| 3 | CRITICAL | 紧急优先级，立即执行 |

## 任务状态机

```
PENDING → QUEUED → RUNNING → COMPLETED
                   → RUNNING → FAILED
                   → RUNNING → TIMEOUT
QUEUED  → CANCELLED
PENDING → CANCELLED
```