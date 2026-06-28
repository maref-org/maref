---
name: security-audit-scan
description: Run security audit scans and fix identified vulnerabilities
allowedTools: [ObserveTool, DiagnoseTool, SearchTool, CodegenTool, VerifyTool, DeployTool]
model: claude-sonnet-4-20250514
maxTurns: 30
---

## Goal
Audit and remediate security vulnerabilities.

## Steps
1. Run `ObserveTool` for full system snapshot
2. Run security-specific diagnostics:
   a. Hardcoded credential scan
   b. Dependency vulnerability check
   c. AST-based dangerous pattern detection
3. For each finding:
   a. Confirm severity
   b. Propose fix via `CodegenTool`
   c. Apply fix only if confidence > 0.9
4. Re-run scan to confirm remediation
5. Report findings fixed, open issues, severity distribution
