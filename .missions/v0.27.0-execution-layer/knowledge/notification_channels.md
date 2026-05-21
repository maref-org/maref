# 通知通道配置指南

## 概述
MAREF 通知系统提供可插拔的通知通道抽象，支持 Email、Webhook、CLI 三种通知方式。

## 快速开始

```python
from maref.executor.notifications import (
    NotificationManager,
    EmailChannel,
    WebhookChannel,
    CLINotificationChannel,
)

manager = NotificationManager()

# 注册 CLI 通道（终端输出）
manager.register_channel("cli", CLINotificationChannel(use_rich=True))

# 发送通知
manager.notify_all("任务完成", "任务 #123 已成功执行", level="info")
```

## 通道配置

### EmailChannel

```python
import os
from maref.executor.notifications import EmailChannel

channel = EmailChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=465,
    username="user@gmail.com",
    password=os.environ["SMTP_PASSWORD"],  # 从环境变量读取
    from_addr="user@gmail.com",
    to_addrs=["team@example.com"],
    use_tls=True,  # SMTP_SSL (端口 465) 或 SMTP (端口 587)
)
```

### WebhookChannel

```python
from maref.executor.notifications import WebhookChannel

channel = WebhookChannel(
    url="https://hooks.example.com/maref",
    headers={"Authorization": "Bearer token123"},
    timeout=10.0,  # 超时秒数
)
```

发送的 JSON payload:
```json
{
  "title": "通知标题",
  "message": "通知内容",
  "level": "info"
}
```

### CLINotificationChannel

```python
from maref.executor.notifications import CLINotificationChannel

# Rich 模式（带 Panel 边框）
channel = CLINotificationChannel(use_rich=True)

# 普通 print 模式
channel = CLINotificationChannel(use_rich=False)
```

## 多通道组合

```python
manager = NotificationManager()
manager.register_channel("email", email_channel)
manager.register_channel("webhook", webhook_channel)
manager.register_channel("cli", cli_channel)

# 同时通知所有通道
results = manager.notify_all(
    "任务失败",
    "任务 #456 执行超时，请检查日志",
    level="error",
)

# results: {"email": True, "webhook": False, "cli": True}
```

## 与 WorkerPool 集成

```python
from maref.executor.queue import TaskQueue
from maref.executor.worker import WorkerPool
from maref.executor.notifications import NotificationManager, CLINotificationChannel

queue = TaskQueue("/tmp/tasks.db")
manager = NotificationManager()
manager.register_channel("cli", CLINotificationChannel())

def task_handler(task):
    # 执行任务逻辑
    result = do_work(task)
    # 发送通知
    manager.notify_all(
        f"任务 {task.name} 完成",
        f"任务 {task.id} 执行成功",
    )
    return result

pool = WorkerPool(queue, num_workers=2)
pool.register_handler("default", task_handler)
pool.start()
```