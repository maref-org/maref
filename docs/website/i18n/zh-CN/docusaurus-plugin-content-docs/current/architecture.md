---
sidebar_position: 3
title: 架构
description: MAREF 六层治理架构
---

# MAREF Architecture

> Version: v0.34.0-rc | Last updated: 2026-06-17

## Overview

MAREF provides six-layer governance, formal model checking via TLA+, a 10-state 4-bit Gray-code governance FSM (with a 24-state 5-bit agent FSM), dual-protocol communication (A2A + MCP), and a full audit/security/compliance infrastructure.

## Six-Layer Governance

```
Layer         Direction       Governance Role
─────         ─────────       ───────────────
天极 (Heaven)  ↓              宪法、元规则、不可修改的红线
人极 (Human)   ─              人类审批、HITL/HOTL/HATL
地极 (Earth)   ↑              零信任安全底座、最小权限
经卦 (Trigram) ↓              角色编排、动态组合
别卦 (Hexagram)─              能力契约、约束止行
爻变 (Change)  ↑              自我演化、变异创新
```

## Core Runtime

Five architectural layers: Meta Layer, Governance Layer, Orchestration Layer, Execution Layer, and Infrastructure Layer — each with distinct responsibilities for governing multi-agent systems.

## Protocols

Dual-protocol architecture: A2A (Agent-to-Agent) for task delegation between agents, and MCP (Model Context Protocol) for tool execution within agents. Both flow through the same governance pipeline.

See the [full architecture document](https://github.com/maref-org/maref/blob/main/docs/architecture.md) for complete details.
