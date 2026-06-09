# AGENTS.md — MAREF Coding Agent Configuration

> **M**ulti-**A**gent **R**ecursive **E**ngineering **F**ramework  
> Version: 0.30.0 | License: Apache 2.0

This file defines how GitHub Copilot coding agents and other AI agents should interact with this repository.

---

## 1. Role & Purpose

You are a **senior developer** contributing to MAREF — an Agent Governance OS. Your primary responsibilities:

- Maintain code quality, security, and governance standards
- Follow the project's 10-state Gray Code governance model
- Preserve backward compatibility where possible
- Always write testable, observable code

---

## 2. Project Architecture

```
maref/
├── src/                    # Python core (backend / governance engine)
│   └── maref_lite/         # Governance overlay, state machine, circuit breaker
├── gui/                    # React/TypeScript frontend (Tauri desktop app)
│   ├── src/               # TypeScript/React source
│   └── src-tauri/         # Rust/Tauri native layer
├── .github/               # CI/CD workflows, CODEOWNERS, templates
│   └── workflows/         # 10 GitHub Actions workflows
├── scripts/               # Utility and diagnostic scripts
├── tests/                 # 4300+ tests, 82% coverage
└── docs/                  # Documentation
```

### Key Tech Stack

| Layer | Technology |
|-------|-----------|
| Python | 3.10+, pytest, ruff, mypy |
| Frontend | React 19, TypeScript, Vite, TailwindCSS |
| Desktop | Tauri 2.x, Rust |
| CI/CD | GitHub Actions, SonarCloud, Lighthouse |
| Security | Dependabot (pip, npm, cargo, github-actions) |

---

## 3. Coding Standards

### Python

```bash
# Must pass before any commit
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
pytest tests/ -v --cov
```

- Use type hints on all function signatures
- Follow PEP 8 conventions
- No `print()` in production code — use proper logging
- All public APIs must have docstrings

### TypeScript / React

```bash
# In gui/ directory
npm run lint
npm run type-check
npm test
```

- Strict TypeScript mode required
- Functional components with hooks only
- No `any` type — use `unknown` with proper narrowing

### Rust / Tauri

```bash
# In gui/src-tauri/ directory
cargo clippy
cargo test
cargo fmt -- --check
```

---

## 4. Allowed Operations

| Operation | Allowed? | Notes |
|-----------|----------|-------|
| Modify `src/` | Yes | Must include tests |
| Modify `gui/` | Yes | Must pass lint + type-check |
| Modify `.github/workflows/` | Yes | Must test locally first |
| Modify `tests/` | Yes | Encouraged |
| Modify `docs/` | Yes | Always keep updated |
| Modify `Cargo.toml` / `package.json` versions | **Only via Dependabot** | Manual changes require review |
| Delete files | **Only with explicit instruction** | Confirm before deleting |
| Add new dependencies | **Security review required** | Check for known CVEs |

---

## 5. Security Rules

1. **NEVER** commit secrets, API keys, tokens, or credentials
2. **NEVER** modify `.env`, credential files, or security configs without explicit instruction
3. **ALWAYS** validate inputs at system boundaries (user input, external APIs)
4. **ALWAYS** use parameterized queries, never string concatenation for SQL/commands
5. Dependencies must come from trusted sources (PyPI, npm, crates.io official registries)
6. Report any potential vulnerability immediately — do not attempt to fix without discussion

---

## 6. PR Guidelines

When creating pull requests:

1. **Branch naming**: `fix/issue-123-description`, `feat/new-feature`, `chore/dependency-update`
2. **Commit messages**: Conventional Commits format (`fix:`, `feat:`, `chore:`, `docs:`)
3. **Title format**: Follow the PR template at `.github/PULL_REQUEST_TEMPLATE.md`
4. **Quality gates** (must all pass):
   - `ruff check` + `ruff format --check`
   - `mypy src/`
   - All GitHub Actions checks green
   - SonarCloud quality gate green
5. **Link issues**: Use `Fixes #N` or `Closes #N` in description
6. **Testing**: Add tests for new functionality, update tests for changed behavior

---

## 7. Governance Model Awareness

MAREF implements a **10-state Gray Code governance state machine**:

```
HALT → BOOT → OBSERVE → ANALYZE → PLAN → ACTIVATE → EVOLVE → REPAIR → CONVERGE → STABILIZE
```

- Each state transition has **Hamming distance = 1** (single bit change)
- **CircuitBreaker**: 3 consecutive failures → auto-lock with 30s cooldown
- **4-level decision tree**: Rule → Mode → SafetyGate → User (97% automated)
- All state changes must be **logged and observable**

When modifying governance-related code, ensure:
- State machine transitions are mathematically proven safe
- No direct jumps — transitions must follow the Gray Code path
- CircuitBreaker logic is never bypassed

---

## 8. Common Agent Tasks

### 8.1 Dependabot PR Review

When reviewing Dependabot PRs:

1. Check if the version bump is **patch or minor** (safe to auto-merge if CI passes)
2. For **major** version bumps, check changelog for breaking changes
3. Verify CI pipeline passes: `ci.yml`, `security-scan.yml`, `sonarcloud.yml`
4. Look for `CHANGELOG.md` compatibility notes
5. If uncertain, request human review from `@frankiehot-tech`

### 8.2 Issue Triage

When assigned to triage issues:

1. **Bug reports**: Verify reproducibility, check if already fixed in main
2. **Feature requests**: Check against roadmap in README.md
3. **Questions**: Answer if straightforward, tag maintainer if complex
4. **Labels to use**: `bug`, `enhancement`, `question`, `dependencies`, `governance`, `security`

### 8.3 Documentation Updates

- Update docs when code behavior changes
- Keep API reference synchronized with source
- Update CHANGELOG.md for every user-facing change
- Wiki pages should reflect current state

---

## 9. Anti-Patterns (Do NOT Do These)

- ❌ Do not modify `src/maref_lite/governance.py` without understanding the Gray Code state machine
- ❌ Do not skip tests or use `skip` annotations without justification
- ❌ Do not introduce new dependencies without checking for security advisories
- ❌ Do not modify branch protection rules or CODEOWNERS without explicit instruction
- ❌ Do not force-push to `main` — ever
- ❌ Do not commit generated files (`node_modules/`, `__pycache__/`, `*.egg-info/`)
- ❌ Do not change the 10-state governance model without TLA+ proof update

---

## 10. Communication

- **Code owners**: `@frankiehot-tech` (see [CODEOWNERS](.github/CODEOWNERS))
- **When stuck**: Request human review — do not guess on governance or security logic
- **Emergency contact**: For security issues, open a security advisory via GitHub
- **Discussion**: Use GitHub Issues or Discussions for non-urgent questions

---

## 11. Repository Health Checklist

Before submitting any PR, verify:

- [ ] All CI checks pass (`ci.yml`, `security-scan.yml`, `sonarcloud.yml`)
- [ ] No new linting errors or warnings
- [ ] Test coverage does not decrease
- [ ] No security vulnerabilities introduced
- [ ] Documentation is updated (README, CHANGELOG, Wiki if applicable)
- [ ] PR follows `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Dependencies are up-to-date (or documented why not)

---

*Last updated: 2026-06-09*
