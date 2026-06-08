# Cryptography Law Compliance Audit

## Applicable Regulations

| Regulation | Jurisdiction | Applicability |
|------------|-------------|---------------|
| Cryptography Law of the PRC (2020) | China | Stub implementations only |
| EU Cyber Resilience Act | EU | Not applicable (open source) |
| Wassenaar Arrangement | International | Open source exemption |

## Cryptographic Usage Inventory

| Algorithm | Module | Type | Production Readiness |
|-----------|--------|------|---------------------|
| SM2 (GB/T 32918) | `src/maref/crypto/sm2.py` | Public-key signature | Stub (hashlib stand-in) |
| SM3 (GB/T 32905) | `src/maref/crypto/sm3.py` | Cryptographic hash | Stub (hashlib stand-in) |
| SM4-GCM (GB/T 32907) | `src/maref/crypto/sm4_gcm.py` | Block cipher (GCM) | Stub (AES-GCM stand-in via cryptography lib) |
| SHA-256 | `hashlib` (stdlib) | General-purpose hash | Production |
| HMAC-SHA256 | `hashlib` (stdlib) | Audit integrity | Production |

## China Cryptography Law Compliance

Per the Cryptography Law of the PRC (Article 25-27):

- **Commercial cryptography**: MAREF uses SM2/SM3/SM4-GCM as commercial
  cryptographic algorithms. Current implementations are stubs using
  stdlib `hashlib` and `cryptography` — not certified SM implementations.
- **Certification**: Production deployment requiring GM/T standards
  compliance must integrate gmssl or a certified SM library.
- **Self-declaration**: This audit serves as the mandatory
  self-declaration record per Article 27.

## Recommended Actions for Production

1. Replace stub implementations with gmssl library (`pip install gmssl`)
2. Conduct SM certification testing with a CNCA-accredited lab
3. File commercial cryptography self-declaration with the CCCA

## Change Log

| Date | Change |
|------|--------|
| 2026-06-06 | Initial audit — all crypto modules are stubs |
