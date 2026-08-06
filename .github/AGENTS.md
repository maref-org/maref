# AGENTS.md — MAREF Coding Agent Configuration

> **M**ulti-**A**gent **R**ecursive **E**volution **F**ramework  
> Version: 0.36.0-rc | License: Apache 2.0

This file defines how AI coding agents should interact with this repository.

## 1. Role & Purpose

You are a senior developer contributing to MAREF — an Agent Governance OS. Your primary responsibilities:

- Maintain code quality, security, and governance standards
- Follow the project's I Ching-based governance model
- Preserve backward compatibility where possible
- Always write testable, observable code

## 2. Key Tech Stack

| Layer | Technology |
|-------|-----------|
| Python | 3.10+, pytest, ruff, mypy strict |
| Frontend | React 19, TypeScript, Vite, TailwindCSS |
| Desktop | Tauri 2.x, Rust |
| CI/CD | GitHub Actions, CodeQL, SonarCloud |
| Security | Bandit, Semgrep, TruffleHog, pip-audit |
| Formal | TLA+ (TLC model checker) |

## 3. Coding Standards

### Python

```bash
# Must pass before any commit
ruff check src/
ruff format --check src/
mypy src/
```

- Use type hints on all function signatures
- Follow PEP 8 conventions
- No `print()` in production code — use `structlog`
- All public APIs must have docstrings

### TypeScript / React

```bash
# In gui/ directory
pnpm lint
pnpm typecheck
pnpm build
```

- Use TypeScript strict mode
- Prefer function components with hooks
- Use TailwindCSS for styling

## 4. Commit Convention

```
type(scope): description

feat:     new feature
fix:      bug fix
chore:    maintenance, deps, config
docs:     documentation
test:     tests
refactor: code restructuring
style:    formatting (ruff/prettier)
```

## 5. PR Requirements

- All CI checks must pass
- At least 1 approving review
- No new ruff/mypy errors
- Tests must include coverage for changes
- D1 gate must pass for release branches
