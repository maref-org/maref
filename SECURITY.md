# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues to the MAREF security team via email.
Include as much detail as possible: affected component, steps to reproduce,
potential impact, and suggested fix if available.

You will receive a response within 48 hours. We will keep you updated on
the remediation progress and credit you in the security advisory (unless
you request anonymity).

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 0.20.x  | ✅ Active support |
| 0.17.x  | ✅ Security fixes |
| < 0.17  | ❌ End of life    |

## Security Architecture

MAREF implements an **8-layer defense-in-depth** architecture for desktop
agent security. See [MAREF Security Whitepaper](docs/MAREF-Security-Whitepaper.md)
for full details.

Key security features:
- **4-Level Policy Decision Tree**: 97% automated safety decisions
- **CircuitBreaker**: 3 consecutive failures trigger automatic lockout
- **RedactionEngine**: Automatic screenshot redaction of sensitive content
- **AuditLogger**: Append-only, HMAC-signed audit trail
- **TLA+ Formal Verification**: Mathematically proven safety properties
- **DID/VC Identity**: Cryptographic agent identity and trust scoring

## Security Best Practices

When deploying MAREF in production:

1. Always run with `MAREF_SAFETY_LEVEL=production`
2. Enable all 8 defense layers (they are on by default)
3. Grant only the minimum required OS permissions
4. Review audit logs regularly (`maref audit show --last 100`)
5. Monitor CircuitBreaker trip rate via Prometheus
6. Keep dependencies updated (`pip list --outdated`)
