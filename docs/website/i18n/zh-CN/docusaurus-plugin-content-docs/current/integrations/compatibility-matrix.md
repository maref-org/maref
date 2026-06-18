---
sidebar_position: 10
title: 兼容性矩阵
description: MAREF 集成的框架与协议兼容性
---

# 框架兼容性矩阵

MAREF 通过标准协议与所有主流多 Agent 框架集成。

## 框架支持

| 框架 | 版本 | 协议 | 状态 |
|-----------|---------|----------|--------|
| LangGraph | >=0.1.0 | MCP | 生产就绪 |
| CrewAI | >=0.30.0 | MCP | 生产就绪 |
| AutoGen | >=0.2.0 | MCP | 生产就绪 |
| OpenAI Agents SDK | >=1.0.0 | MCP | 生产就绪 |
| Claude Code | 最新 | MCP | 生产就绪 |
| Cursor | 最新 | MCP | 生产就绪 |
| Windsurf | 最新 | MCP | 生产就绪 |
| Trae CN | 最新 | MCP | 生产就绪 |
| Dify | >=0.6.0 | MCP | 测试版 |
| Coze | 最新 | MCP | 测试版 |
| GitHub Copilot | 最新 | MCP | 测试版 |

## 协议支持

| 协议 | 版本 | 状态 |
|----------|---------|--------|
| MCP（模型上下文协议） | 2025-03-26 | 生产就绪 |
| A2A（Agent 间通信协议） | v0.3 | 生产就绪 |
| OpenTelemetry | 1.24+ | 生产就绪 |

## 状态定义

- **生产就绪**：已在生产部署中通过测试并获得支持
- **测试版**：功能可用，但可能存在正在积极处理的边缘情况
