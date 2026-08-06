---
name: detect-and-remove-dead-code
description: Detect and remove unused imports, dead functions, and orphaned symbols
allowedTools: [DiagnoseTool, SearchTool, ReadFileTool, EditFileTool, VerifyTool]
model: claude-sonnet-4-20250514
maxTurns: 20
---

## Goal
Clean up dead code across the codebase.

## Steps
1. Run `DiagnoseTool` with unused-import analysis
2. For each suspect file:
   a. Read the file
   b. Confirm symbol is unused (SearchTool cross-reference)
   c. Remove unused import/function/class
3. Run test suite to verify no regressions
4. Report bytes saved and modules cleaned
