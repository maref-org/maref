# Contributing to MAREF

Thank you for considering contributing to MAREF! We welcome contributions from everyone.

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## How to Contribute

### 1. Fork the Repository

Fork the repository to your own GitHub account.

### 2. Clone the Repository

```bash
git clone https://github.com/<your-username>/maref.git
cd maref
```

### 3. Create a Branch

Create a branch for your changes:

```bash
git checkout -b feature/your-feature-name
```

### 4. Make Changes

Make your changes and ensure they follow our coding standards:
- Python: PEP 8 + ruff + mypy strict mode
- TypeScript: ESLint + TypeScript strict mode

### 5. Run Tests

```bash
# Run unit tests
pytest tests/ -v --cov=src/maref

# Run security tests
pytest tests/security/ -v

# Type checking
mypy src/

# Linting
ruff check src/
```

### 6. Commit Changes

```bash
git add .
git commit -m "feat(module): description of your changes"
```

### 7. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request from your branch to the main branch.

## Issue Guidelines

### Bug Reports

- Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md)
- Include steps to reproduce
- Include expected and actual behavior
- Include environment information

### Feature Requests

- Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md)
- Describe the use case
- Provide a proposed solution

## PR Guidelines

- Use the [PR template](.github/PULL_REQUEST_TEMPLATE.md)
- Reference related issues using `Fixes #123`
- Include tests for your changes
- Ensure all existing tests pass
- Keep PRs focused on a single change

## Code Review Process

1. PR is submitted
2. CI/CD runs automatically
3. Reviewers are assigned
4. Feedback is provided
5. Changes are made if needed
6. PR is merged

## Getting Help

If you need help, feel free to ask in [Discussions](https://github.com/maref-org/maref/discussions) or create a [Question issue](.github/ISSUE_TEMPLATE/question.md).
