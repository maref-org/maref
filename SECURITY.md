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
| 0.30.x  | ✅ Active support |
| 0.20.x  | ✅ Security fixes |
| < 0.20  | ❌ End of life    |

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

## Cryptographic Compliance & Export Control

### Chinese National Cryptographic Standards (国密算法)

MAREF includes implementations of Chinese national cryptographic standards
for compliance with **GB/T 32918** and participation in the **AIP (AI Agent
Protocol) Pioneer Program**.

| Algorithm | Standard | Implementation | File |
|-----------|----------|----------------|------|
| SM2 | GB/T 32918.2-2016 | Elliptic curve public key cryptography | `src/maref/crypto/sm2.py` |
| SM3 | GB/T 32918.1-2016 | Cryptographic hash function (256-bit) | `src/maref/crypto/sm3.py` |
| SM4-GCM | GB/T 32907-2016 | Block cipher with authenticated encryption | `src/maref/crypto/sm4_gcm.py` |

### Export Control Notice

**WARNING**: The SM2/SM3/SM4-GCM implementations in this repository are
subject to **Chinese cryptographic export control regulations** (密码出口管制).

- **Within China**: Free to use, modify, and distribute under Apache-2.0
- **Outside China**: Users are responsible for ensuring compliance with
  local cryptographic import/export laws. MAREF provides these algorithms
  for interoperability and standards compliance only.
- **Dual-use**: These algorithms are classified as dual-use technology
  under Wassenaar Arrangement Category 5 Part 2. Users in jurisdictions
  with export control restrictions must obtain appropriate licenses before
  redistribution.

### Disclaimer

MAREF is an open-source reference implementation. The inclusion of SM2/SM3/SM4
**does not constitute** an official endorsement by Chinese regulatory bodies.
Users must conduct their own compliance assessment for production deployments.

## Security Best Practices

When deploying MAREF in production:

1. Always run with `MAREF_SAFETY_LEVEL=production`
2. Enable all 8 defense layers (they are on by default)
3. Grant only the minimum required OS permissions
4. Review audit logs regularly (`maref audit show --last 100`)
5. Monitor CircuitBreaker trip rate via Prometheus
6. Keep dependencies updated (`pip list --outdated`)
