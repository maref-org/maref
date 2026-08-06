---
sidebar_position: 1
title: LangGraph 集成
description: 将 MAREF 治理应用于 LangGraph Agent
---

# 将 MAREF 治理与 LangGraph 集成

本指南展示如何通过 A2A 桥接将 MAREF 治理应用于 LangGraph Agent，为其包装安全门、审计日志、断路器保护和人工监督。

## 概述

LangGraph 提供有状态的多步 Agent 工作流。MAREF 治理为每个图节点转换添加安全门、审计日志、断路器保护和人工监督（HITL）。

## 基础设置

```python
from langgraph.graph import StateGraph
from sidecar.adapters.langgraph import LangGraphAdapter

graph = StateGraph(MyState)
graph.add_node("process", process_node)
graph.add_edge("process", "human_review")

adapter = LangGraphAdapter(graph)

decision, reason = adapter.evaluate_node_safety("human_review", current_state)
if decision == "block":
    print(f"Transition blocked: {reason}")
else:
    adapter.observe_transition("human_review", from_state="process")
    state = adapter.inject_governance("human_review", current_state, decision, reason)
```

## 主要特性

- 图节点转换前的安全评估
- 任意图节点的治理注入
- 每次节点转换的审计日志记录
- 故障隔离的断路器集成

## 状态机集成

LangGraph 状态与 MAREF 的 10 状态机同步：
- process → ANALYZE
- review → EVALUATE
- decide → DECIDE
- execute → ACT
- verify → VERIFY

查看 [GitHub 源码](https://github.com/maref-org/maref/blob/main/docs/integrations/langgraph.md) 获取最新集成代码。
