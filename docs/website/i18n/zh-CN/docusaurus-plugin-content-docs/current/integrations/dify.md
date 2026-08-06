---
sidebar_position: 4
title: Dify 集成
description: 将 MAREF 治理应用于 Dify 工作流
---

# 将 MAREF 治理与 Dify 集成

本指南展示如何将 MAREF 治理与 Dify 工作流和自定义工具一起使用，为 Dify API 调用包装治理决策、审计日志和断路器保护。

## 概述

Dify 提供可视化 AI 工作流构建器，支持 LLM 编排。MAREF 治理为每个 Dify 工作流节点和 API 调用添加安全评估、风险评估和合规审计。

## 基础设置

```python
from sidecar.adapters.dify import DifyAdapter

adapter = DifyAdapter(
    api_key="dify-app-key",
    base_url="http://localhost:8000",
)

decision, reason = adapter.evaluate_workflow_safety(
    workflow_id="wf-001",
    input_data={"query": "Delete user records"},
)
if decision == "block":
    print(f"Workflow blocked: {reason}")
else:
    result = adapter.execute_with_governance(
        workflow_id="wf-001",
        input_data={"query": "Show user stats"},
    )
```

## 主要特性

- 执行前工作流安全评估
- Dify API 调用的治理包装
- 所有工作流执行的审计日志
- API 故障隔离的断路器集成

## 断路器保护

```python
from sidecar.adapters.dify import DifyAdapter
from maref.governance.circuit_breaker import CircuitBreaker

adapter = DifyAdapter(
    api_key="dify-app-key",
    base_url="http://localhost:8000",
    circuit_breaker=CircuitBreaker(max_consecutive_failures=3),
)
```

查看 [GitHub 源码](https://github.com/maref-org/maref/blob/main/docs/integrations/dify.md) 获取最新集成代码。
