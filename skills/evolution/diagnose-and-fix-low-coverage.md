---
name: diagnose-and-fix-low-coverage
description: Detect modules below coverage threshold and generate tests
allowedTools: [ObserveTool, DiagnoseTool, CodegenTool, VerifyTool, EditFileTool]
model: claude-sonnet-4-20250514
maxTurns: 30
---

## Goal
Improve test coverage in identified low-coverage modules.

## Steps
1. Run `ObserveTool` to get current coverage snapshot
2. Run `DiagnoseTool` to identify modules below threshold
3. For each low-coverage module:
   a. Read existing test patterns
   b. Generate missing tests
   c. Verify with pytest
4. Report coverage delta
