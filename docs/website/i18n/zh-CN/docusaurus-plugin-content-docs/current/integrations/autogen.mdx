---
sidebar_position: 3
title: AutoGen 集成
description: 将 MAREF 治理应用于 AutoGen Agent
---

# 将 MAREF 治理与 AutoGen 集成

本指南展示如何将 MAREF 治理应用于 AutoGen Agent，为对话包装审计日志、风险评估和断路器保护。

## 概述

AutoGen 支持具有灵活 Agent 团队的多 Agent 对话。MAREF 治理为每次 Agent 交互添加消息级观察、治理注入和完整审计追踪。

## 基础设置

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision

team = RoundRobinGroupChat(agents=[agent1, agent2])
adapter = AutoGenAdapter(team)

async for msg in adapter.observe_stream(team.run_stream(task="...")):
    if isinstance(msg, TaskResult):
        break

msg = {"content": "rm -rf /important"}
msg = adapter.inject_governance(msg, GovernanceDecision.BLOCK, "destructive command")
```

## 主要特性

- 实时消息流观察
- 治理注入 Agent 消息
- 自动安全检查所有内容
- 与 MAREF 状态机和审计日志集成

## 完整示例

```python
import asyncio
from autogen_agentchat.teams import RoundRobinGroupChat
from sidecar.adapters.autogen import AutoGenAdapter, GovernanceDecision

async def run_governed_conversation():
    team = RoundRobinGroupChat(agents=[agent1, agent2])
    adapter = AutoGenAdapter(team)
    async for msg in adapter.observe_stream(team.run_stream(task="Analyze data")):
        if isinstance(msg, TaskResult):
            break
    print(f"Audit entries: {adapter.get_audit_count()}")

asyncio.run(run_governed_conversation())
```

## HITL 集成

```python
adapter = AutoGenAdapter(team)
msg = {"content": "delete /important/data"}
decision = adapter.inject_governance(msg, GovernanceDecision.BLOCK, "destructive command")
if decision == GovernanceDecision.BLOCK:
    adapter.override_decision(msg, GovernanceDecision.ALLOW, reviewer="admin")
```

## 断路器保护

```python
from maref.governance.circuit_breaker import CircuitBreaker
adapter = AutoGenAdapter(team, circuit_breaker=CircuitBreaker(max_consecutive_failures=3))
```

查看 [GitHub 源码](https://github.com/maref-org/maref/blob/main/docs/integrations/autogen.md) 获取最新集成代码。
