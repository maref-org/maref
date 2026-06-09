# GitHub Copilot Instructions — MAREF

This repository is part of the Athena ecosystem. All code must comply with
the Athena System Constitution v1.5.

## Rules
1. No internal paths (/Volumes/, /Users/) in committed code
2. No API keys, tokens, or credentials in source
3. No exact timestamps with microsecond precision
4. Follow existing code patterns (ruff + mypy strict for Python)
5. MCP tools must include api_version in input_schema
6. Cross-boundary MCP calls must have FAIL_MODE configured
7. This is Track B — sync direction is A→B only

## Reference
- Constitution: ../../CONSTITUTION.md
