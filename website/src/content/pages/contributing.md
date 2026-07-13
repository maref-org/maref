# Contributing to MAREF

Thank you for contributing to the Multi-Agent Recursive Evolution Framework.

## Development Setup

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,desktop]"
```

## Code Style

- **ruff**: `ruff check src tests` — 0 violations required
- **mypy**: `mypy src/` — strict type checking with `disallow_untyped_defs=true`
- **Python**: 3.10+ with `from __future__ import annotations`
- **Docstrings**: Google style (`[tool.ruff.lint.pydocstyle] convention = "google"`)

## Testing

```bash
# Full test suite
pytest tests/ -v --cov

# Specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/desktop/ -v
pytest tests/security/ -v
pytest tests/benchmark/ -v

# New features require >= 90% coverage
pytest tests/ -v --cov --cov-report=term --cov-fail-under=90
```

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for your changes
3. Run `ruff check src tests` and `mypy src/` — both must be clean
4. Run `pytest tests/ -v --cov` — all tests must pass
5. Update CHANGELOG.md under the `## Unreleased` section
6. Submit a PR with a descriptive title and body

## PR Template

```markdown
## Summary
Brief description of changes.

## Type
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Performance improvement
- [ ] Security fix

## Verification
- [ ] ruff clean (`ruff check src tests`)
- [ ] mypy clean (`mypy src/`)
- [ ] Tests pass (`pytest tests/ -v --cov`)
- [ ] New tests added for changed functionality
```

## Commit Messages

Follow conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation
- `test:` adding tests
- `refactor:` code restructuring
- `perf:` performance improvement
- `security:` security-related changes

## Code Review

All PRs require at least one approving review before merge. Reviewers check for:
1. Code correctness and safety implications
2. Test coverage and quality
3. Style consistency (ruff + mypy)
4. Documentation completeness
