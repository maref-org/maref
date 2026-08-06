---
sidebar_position: 2
title: CrewAI 集成
description: 将 MAREF 治理应用于 CrewAI Crews
---

# 将 MAREF 治理与 CrewAI 集成

本指南展示如何将 MAREF 治理应用于 CrewAI Crews，为任务执行包装治理决策、审计日志和断路器保护。

## 概述

CrewAI 支持协作式 AI Agent 团队。MAREF 治理为每次 Crew 操作添加任务级安全评估、Agent 活动观察和防篡改审计追踪。

## 基础设置

```python
from crewai import Crew, Agent, Task
from sidecar.adapters.crewai import CrewAIAdapter

crew = Crew(agents=[agent], tasks=[task])
adapter = CrewAIAdapter(crew)

decision, reason = adapter.evaluate_task_safety(task.description)
if decision == "block":
    print(f"Task blocked: {reason}")
else:
    task = adapter.inject_governance(task, decision, reason)
    crew.kickoff()

adapter.observe_agent_activity(agent.role, task.description)
state = await adapter.get_state(AgentId(name=agent.role, namespace="crewai"))
```

## 主要特性

- 执行前任务安全评估
- 执行后 Agent 活动观察
- 任务上下文治理注入
- 自动状态机集成

## HITL 集成

```python
adapter = CrewAIAdapter(crew)
decision, reason = adapter.evaluate_task_safety("Deploy to production")
if decision == "ask_user":
    event_id = adapter.request_human_approval("deploy_to_prod", "Deploy to production env")
    adapter.approve_operation(event_id, reviewer="ops-admin")
```

查看 [GitHub 源码](https://github.com/maref-org/maref/blob/main/docs/integrations/crewai.md) 获取最新集成代码。
