---
name: optimize-bottleneck-module
description: Profile and optimize identified performance bottlenecks
allowedTools: [DiagnoseTool, ArchitectTool, CodegenTool, EditFileTool, BenchmarkTool]
model: claude-sonnet-4-20250514
maxTurns: 40
---

## Goal
Improve performance of bottleneck modules.

## Steps
1. Run `DiagnoseTool` to identify slow modules and hot paths
2. Run `ArchitectTool` to propose optimization strategies
3. Review and select optimization approach
4. Apply optimizations via `CodegenTool`
5. Benchmark before/after to measure improvement
6. Run full test suite to verify correctness
7. Report performance delta (wall time, memory, throughput)
