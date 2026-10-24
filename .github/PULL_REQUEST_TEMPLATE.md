---
name: Pull Request
about: Submit a PR to contribute to MAREF
labels: 'triage'
assignees: ''
---

## Description
Describe what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Infrastructure (CI/CD, scripts, etc.)

## Related Issues
Link any related issues using `Fixes #123` or `Closes #123`.

## Testing
How did you test this change?
- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing
- [ ] No tests needed

## Audit System Resilience
> Required for any change touching audit, meta-monitor, paths, or governance gates (S-04).
> If this audit system goes down, who or what detects it, and how?

- [ ] The failure detector is described below (not just "tests pass")
- [ ] Detector has an owner/runbook or is covered by M0/M1/M2/CI

Detector / runbook:

## Checklist
- [ ] I have read the [contributing guidelines](CONTRIBUTING.md)
- [ ] My code follows the project's coding standards
- [ ] I have added tests that verify my changes
- [ ] All existing tests pass
- [ ] I have updated the documentation if needed
- [ ] My changes do not introduce any security vulnerabilities
