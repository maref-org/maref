# EAR Export Control Compliance

## Statement

MAREF v0.30.0-GA is an open-source software project released under the
Apache-2.0 license. It is published to GitHub at https://github.com/maref-org/maref
for public access.

## Classification

- **EAR Category**: EAR99 (not subject to ECCN controls)
- **Jurisdiction**: Not subject to ITAR
- **Reason**: Published open-source software with no encryption
  functionality that qualifies under TSU/EAR 734.3(b)(3).
  Cryptographic modules (SM2/SM3/SM4-GCM) are stub implementations
  using high-level `hashlib` and `cryptography` wrappers — not
  standalone cryptographic implementations.

## Open Source Exemption

Per EAR 734.3(b)(3), software that is published and publicly available
(including via GitHub) is not subject to the EAR. No export license is
required.

## Encryption Registration

Encryption Registration with BIS is not required because:
1. The project is publicly available open-source code
2. Cryptographic functions are educational stub implementations
3. No proprietary encryption technology is distributed

## Contact

For export control questions: https://github.com/maref-org/maref/issues
